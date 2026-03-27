"""
Tests conversion sacs -> kg et kg -> sacs (boutique) + idempotence.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APITestCase

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock, convertir_kg_en_sac
from produits.models import Categorie, Produit


class StockConversionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        cls.lieu = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique Test", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.user = CustomUser.objects.create_user(
            username="boutique_convert",
            password="b123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu,
        )
        cat = Categorie.objects.create(nom="Cat", entreprise=entreprise)
        cls.produit_sac = Produit.objects.create(
            categorie=cat,
            nom="Farine sac",
            code="FS01",
            unite="sac",
            entreprise=entreprise,
            poids_par_sac=Decimal("50.000"),
        )
        Stock.objects.create(
            produit=cls.produit_sac, lieu=cls.lieu,
            quantite=Decimal("10"), quantite_kg=Decimal("0"),
        )

    def _auth_headers(self):
        refresh = RefreshToken.for_user(self.user)
        return {"HTTP_AUTHORIZATION": f"Bearer {str(refresh.access_token)}"}

    def test_conversion_sac_en_kg(self):
        """Convertit 2 sacs -> 100 kg et met à jour le stock."""
        url = reverse("boutique-stock-convertir", args=[self.produit_sac.pk])
        r = self.client.post(
            url, {"nombre_sacs": 2}, format="json", **self._auth_headers(),
            HTTP_IDEMPOTENCY_KEY="conversion-sac-kg-test-001",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        stock = Stock.objects.get(produit=self.produit_sac, lieu=self.lieu)
        self.assertEqual(stock.quantite, Decimal("8"))
        self.assertEqual(stock.quantite_kg, Decimal("100"))

    def test_conversion_idempotente_via_header(self):
        """Même Idempotency-Key => pas de double débit."""
        url = reverse("boutique-stock-convertir", args=[self.produit_sac.pk])
        headers = {**self._auth_headers(), "HTTP_IDEMPOTENCY_KEY": "conv-001"}
        r1 = self.client.post(url, {"nombre_sacs": 3}, format="json", **headers)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        stock_1 = Stock.objects.get(produit=self.produit_sac, lieu=self.lieu)
        self.assertEqual(stock_1.quantite, Decimal("7"))
        self.assertEqual(stock_1.quantite_kg, Decimal("150"))

        r2 = self.client.post(url, {"nombre_sacs": 3}, format="json", **headers)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        stock_2 = Stock.objects.get(produit=self.produit_sac, lieu=self.lieu)
        self.assertEqual(stock_2.quantite, Decimal("7"))
        self.assertEqual(stock_2.quantite_kg, Decimal("150"))


# ─── Tests service convertir_kg_en_sac ────────────────────────────────────────

class ConvertirKgEnSacServiceTests(TestCase):
    """Tests unitaires du service convertir_kg_en_sac (inventaire/services.py)."""

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS KG SAC")
        cls.lieu = Lieu.objects.create(
            entreprise=entreprise, nom="Dépôt Test", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.user = CustomUser.objects.create_user(
            username="agent_kg_sac",
            password="x",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu,
        )
        cat = Categorie.objects.create(nom="Aliments", entreprise=entreprise)

        # Produit avec poids_par_sac défini (50 kg/sac)
        cls.produit_50 = Produit.objects.create(
            categorie=cat, nom="Maïs 50kg", code="M50", unite="sac",
            entreprise=entreprise, poids_par_sac=Decimal("50.000"),
        )
        # Produit sans poids_par_sac défini
        cls.produit_libre = Produit.objects.create(
            categorie=cat, nom="Son libre", code="SL01", unite="sac",
            entreprise=entreprise, poids_par_sac=None,
        )

    def _make_stock(self, produit, quantite=Decimal("0"), quantite_kg=Decimal("0")):
        return Stock.objects.create(
            produit=produit, lieu=self.lieu,
            quantite=quantite, quantite_kg=quantite_kg,
        )

    # ── Scénario 1 : 100 kg → sacs 25 kg → 4 sacs + 0 kg restants ─────────────
    def test_100kg_sacs25_donne_4sacs_0kg(self):
        s = self._make_stock(self.produit_libre, quantite_kg=Decimal("100"))
        res = convertir_kg_en_sac(s, nombre_sacs=4, poids_par_sac=Decimal("25"), updated_by=self.user)
        self.assertEqual(res["sacs_crees"], 4)
        self.assertEqual(res["kg_debites"], Decimal("100"))
        s.refresh_from_db()
        self.assertEqual(s.quantite, Decimal("4"))
        self.assertEqual(s.quantite_kg, Decimal("0"))

    # ── Scénario 2 : 110 kg → sacs 25 kg → 4 sacs + 10 kg restants ────────────
    def test_110kg_sacs25_donne_4sacs_10kg(self):
        s = self._make_stock(self.produit_libre, quantite_kg=Decimal("110"))
        res = convertir_kg_en_sac(s, nombre_sacs=4, poids_par_sac=Decimal("25"), updated_by=self.user)
        self.assertEqual(res["sacs_crees"], 4)
        self.assertEqual(res["kg_debites"], Decimal("100"))
        s.refresh_from_db()
        self.assertEqual(s.quantite, Decimal("4"))
        self.assertEqual(s.quantite_kg, Decimal("10"))

    # ── Scénario 3 : 50 kg → sac 50 kg → 1 sac + 0 kg ─────────────────────────
    def test_50kg_sac50_donne_1sac(self):
        s = self._make_stock(self.produit_50, quantite_kg=Decimal("50"))
        res = convertir_kg_en_sac(s, nombre_sacs=1, poids_par_sac=Decimal("50"), updated_by=self.user)
        self.assertEqual(res["sacs_crees"], 1)
        self.assertEqual(res["kg_debites"], Decimal("50"))
        s.refresh_from_db()
        self.assertEqual(s.quantite, Decimal("1"))
        self.assertEqual(s.quantite_kg, Decimal("0"))

    # ── Scénario 4 : 30 kg → sac 50 kg → insuffisant ──────────────────────────
    def test_30kg_sac50_insuffisant(self):
        s = self._make_stock(self.produit_50, quantite_kg=Decimal("30"))
        with self.assertRaises(ErreurStock) as cm:
            convertir_kg_en_sac(s, nombre_sacs=1, poids_par_sac=Decimal("50"), updated_by=self.user)
        self.assertIn("insuffisant", str(cm.exception))
        s.refresh_from_db()
        # Aucune modification du stock
        self.assertEqual(s.quantite_kg, Decimal("30"))

    # ── Scénario 5 : Conversion inverse sac → kg → kg → sac (conservation) ────
    def test_conservation_cycle_sac_kg_sac(self):
        from inventaire.services import convertir_sac_en_kg
        s = self._make_stock(self.produit_50, quantite=Decimal("4"), quantite_kg=Decimal("0"))
        # 4 sacs → 200 kg
        convertir_sac_en_kg(s, nombre_sacs=4, updated_by=self.user, idempotency_key="cycle-sac-kg-1")
        s.refresh_from_db()
        self.assertEqual(s.quantite, Decimal("0"))
        self.assertEqual(s.quantite_kg, Decimal("200"))
        # 200 kg → 4 sacs
        convertir_kg_en_sac(s, nombre_sacs=4, poids_par_sac=Decimal("50"), updated_by=self.user)
        s.refresh_from_db()
        self.assertEqual(s.quantite, Decimal("4"))
        self.assertEqual(s.quantite_kg, Decimal("0"))

    # ── Scénario 6 : Isolation poids — produit.poids_par_sac != poids_par_sac ──
    def test_isolation_poids_par_sac_incompatible(self):
        s = self._make_stock(self.produit_50, quantite_kg=Decimal("200"))
        with self.assertRaises(ErreurStock) as cm:
            convertir_kg_en_sac(s, nombre_sacs=4, poids_par_sac=Decimal("25"), updated_by=self.user)
        self.assertIn("Mélange", str(cm.exception))
        s.refresh_from_db()
        self.assertEqual(s.quantite_kg, Decimal("200"))  # stock inchangé

    # ── Scénario 7 : Produit libre — poids quelconque accepté ──────────────────
    def test_produit_libre_poids_quelconque(self):
        s = self._make_stock(self.produit_libre, quantite_kg=Decimal("75"))
        res = convertir_kg_en_sac(s, nombre_sacs=3, poids_par_sac=Decimal("25"), updated_by=self.user)
        self.assertEqual(res["sacs_crees"], 3)
        s.refresh_from_db()
        self.assertEqual(s.quantite_kg, Decimal("0"))
        self.assertEqual(s.quantite, Decimal("3"))

    # ── Scénario 8 : poids_par_sac = 0 → rejeté ────────────────────────────────
    def test_poids_par_sac_zero_rejete(self):
        s = self._make_stock(self.produit_libre, quantite_kg=Decimal("100"))
        with self.assertRaises(ErreurStock):
            convertir_kg_en_sac(s, nombre_sacs=1, poids_par_sac=Decimal("0"), updated_by=self.user)

    # ── Scénario 9 : nombre_sacs = 0 → rejeté ──────────────────────────────────
    def test_nombre_sacs_zero_rejete(self):
        s = self._make_stock(self.produit_libre, quantite_kg=Decimal("100"))
        with self.assertRaises(ErreurStock):
            convertir_kg_en_sac(s, nombre_sacs=0, poids_par_sac=Decimal("25"), updated_by=self.user)


# ─── Tests API kg → sac (boutique endpoint) ────────────────────────────────────

class ConvertirKgEnSacAPITests(APITestCase):
    """Tests de l'endpoint POST /boutique/stock/<id>/convertir-kg-en-sac/."""

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS API KG")
        cls.lieu = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique KG", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.user = CustomUser.objects.create_user(
            username="boutique_kg_api",
            password="x",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu,
        )
        cat = Categorie.objects.create(nom="Grains", entreprise=entreprise)
        cls.produit = Produit.objects.create(
            categorie=cat, nom="Blé 25kg", code="B25", unite="sac",
            entreprise=entreprise, poids_par_sac=Decimal("25.000"),
        )
        cls.token = str(RefreshToken.for_user(cls.user).access_token)

    def setUp(self):
        Stock.objects.filter(produit=self.produit, lieu=self.lieu).delete()
        Stock.objects.create(
            produit=self.produit, lieu=self.lieu,
            quantite=Decimal("0"), quantite_kg=Decimal("200"),
        )

    def _headers(self, idem_key="kg-sac-api-test"):
        return {
            "HTTP_AUTHORIZATION": f"Bearer {self.token}",
            "HTTP_IDEMPOTENCY_KEY": idem_key,
        }

    def test_api_convertit_kg_en_sacs(self):
        url = reverse("boutique-stock-convertir-kg-en-sac", args=[self.produit.pk])
        r = self.client.post(
            url,
            {"nombre_sacs": 4, "poids_par_sac": "25"},
            format="json",
            **self._headers(),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertEqual(data["sacs_crees"], 4)
        self.assertEqual(Decimal(data["kg_debites"]), Decimal("100"))
        s = Stock.objects.get(produit=self.produit, lieu=self.lieu)
        self.assertEqual(s.quantite, Decimal("4"))
        self.assertEqual(s.quantite_kg, Decimal("100"))

    def test_api_stock_insuffisant_retourne_400(self):
        url = reverse("boutique-stock-convertir-kg-en-sac", args=[self.produit.pk])
        r = self.client.post(
            url,
            {"nombre_sacs": 100, "poids_par_sac": "25"},
            format="json",
            **self._headers("kg-insuff"),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_poids_incompatible_retourne_400(self):
        url = reverse("boutique-stock-convertir-kg-en-sac", args=[self.produit.pk])
        r = self.client.post(
            url,
            {"nombre_sacs": 2, "poids_par_sac": "50"},
            format="json",
            **self._headers("kg-poids-bad"),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Mélange", r.json().get("detail", ""))

    def test_api_idempotent(self):
        url = reverse("boutique-stock-convertir-kg-en-sac", args=[self.produit.pk])
        headers = self._headers("kg-idem-001")
        r1 = self.client.post(url, {"nombre_sacs": 2, "poids_par_sac": "25"}, format="json", **headers)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        s_after_1 = Stock.objects.get(produit=self.produit, lieu=self.lieu)

        r2 = self.client.post(url, {"nombre_sacs": 2, "poids_par_sac": "25"}, format="json", **headers)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        s_after_2 = Stock.objects.get(produit=self.produit, lieu=self.lieu)
        # Stock inchangé après la 2e requête idempotente
        self.assertEqual(s_after_1.quantite, s_after_2.quantite)
        self.assertEqual(s_after_1.quantite_kg, s_after_2.quantite_kg)


# ─── Tests isolation poids_par_sac (anti-mélange) ─────────────────────────────

class IsolationPoidsParSacTests(TestCase):
    """
    Vérifie que le système refuse tout mélange de sacs à poids différents.
    Règle métier absolue : sacs 25kg ≠ sacs 50kg — jamais fusionnés.
    """

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS ISO")
        cls.lieu_mpsl = Lieu.objects.create(
            entreprise=entreprise, nom="MPSL Iso", type_lieu=Lieu.TYPE_MPSL
        )
        cls.lieu_boutique = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique Iso", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.user = CustomUser.objects.create_user(
            username="agent_iso", password="x",
            role=CustomUser.ROLE_MPSL, entreprise=entreprise, lieu=cls.lieu_mpsl,
        )
        cat = Categorie.objects.create(nom="Céréales Iso", entreprise=entreprise)
        cls.cat = cat
        cls.entreprise = entreprise
        cls.produit_25 = Produit.objects.create(
            categorie=cat, nom="Maïs iso 25", code="MI25", unite="sac",
            entreprise=entreprise, poids_par_sac=Decimal("25.000"),
        )
        cls.produit_50 = Produit.objects.create(
            categorie=cat, nom="Maïs iso 50", code="MI50", unite="sac",
            entreprise=entreprise, poids_par_sac=Decimal("50.000"),
        )
        cls.produit_libre = Produit.objects.create(
            categorie=cat, nom="Grain libre iso", code="GLI01", unite="sac",
            entreprise=entreprise, poids_par_sac=None,
        )

    # ── Scénario 1 : achat même produit à poids différent avec sacs en stock ──
    def test_achat_mpsl_refuse_melange_pps_avec_sacs_en_stock(self):
        from inventaire.services import enregistrer_achat_mpsl
        # 10 sacs à 25 kg/sac
        enregistrer_achat_mpsl(
            self.lieu_mpsl, "Maïs test mélange achat", Decimal("10"), "sacs",
            poids_par_sac=Decimal("25"), created_by=self.user,
        )
        p = Produit.objects.get(nom__iexact="Maïs test mélange achat", entreprise=self.entreprise)
        self.assertEqual(p.poids_par_sac, Decimal("25"))
        stock = Stock.objects.get(produit=p, lieu=self.lieu_mpsl)
        self.assertEqual(stock.quantite, Decimal("10"))

        # Tenter d'acheter à pps=50 → refusé car sacs pps=25 encore en stock
        with self.assertRaises(ErreurStock) as cm:
            enregistrer_achat_mpsl(
                self.lieu_mpsl, "Maïs test mélange achat", Decimal("5"), "sacs",
                poids_par_sac=Decimal("50"), created_by=self.user,
            )
        self.assertIn("Mélange", str(cm.exception))
        stock.refresh_from_db()
        self.assertEqual(stock.quantite, Decimal("10"))  # inchangé
        p.refresh_from_db()
        self.assertEqual(p.poids_par_sac, Decimal("25"))  # pps non modifié

    # ── Scénario 2 : changement pps autorisé si stock de sacs = 0 ─────────────
    def test_achat_mpsl_permet_changement_pps_si_sacs_a_zero(self):
        from inventaire.services import enregistrer_achat_mpsl, convertir_sac_en_kg
        enregistrer_achat_mpsl(
            self.lieu_mpsl, "Maïs pps ok", Decimal("4"), "sacs",
            poids_par_sac=Decimal("25"), created_by=self.user,
        )
        p = Produit.objects.get(nom__iexact="Maïs pps ok", entreprise=self.entreprise)
        stock = Stock.objects.get(produit=p, lieu=self.lieu_mpsl)
        convertir_sac_en_kg(stock, 4, updated_by=self.user, idempotency_key="iso-sac-kg-2")
        stock.refresh_from_db()
        self.assertEqual(stock.quantite, Decimal("0"))
        # Maintenant autorisé — plus de sacs de l'ancien poids
        enregistrer_achat_mpsl(
            self.lieu_mpsl, "Maïs pps ok", Decimal("3"), "sacs",
            poids_par_sac=Decimal("50"), created_by=self.user,
        )
        p.refresh_from_db()
        self.assertEqual(p.poids_par_sac, Decimal("50"))

    # ── Scénario 3 : kg→sac refuse si sacs existants à poids inconnu ──────────
    def test_kg_en_sac_refuse_si_sacs_existants_pps_inconnu(self):
        stock = Stock.objects.create(
            produit=self.produit_libre, lieu=self.lieu_boutique,
            quantite=Decimal("5"),   # 5 sacs de poids inconnu
            quantite_kg=Decimal("200"),
        )
        with self.assertRaises(ErreurStock) as cm:
            convertir_kg_en_sac(
                stock, nombre_sacs=4, poids_par_sac=Decimal("25"), updated_by=self.user
            )
        self.assertIn("poids non défini", str(cm.exception))
        stock.refresh_from_db()
        self.assertEqual(stock.quantite_kg, Decimal("200"))  # inchangé

    # ── Scénario 4 : kg→sac fixe pps sur produit si aucun sac existant ────────
    def test_kg_en_sac_verrouille_pps_sur_produit_si_aucun_sac(self):
        produit_neutre = Produit.objects.create(
            categorie=self.cat, nom="Grain neutre fixpps", code="GNF02",
            unite="sac", entreprise=self.entreprise, poids_par_sac=None,
        )
        stock = Stock.objects.create(
            produit=produit_neutre, lieu=self.lieu_boutique,
            quantite=Decimal("0"), quantite_kg=Decimal("100"),
        )
        convertir_kg_en_sac(stock, nombre_sacs=2, poids_par_sac=Decimal("25"), updated_by=self.user)
        stock.refresh_from_db()
        produit_neutre.refresh_from_db()
        self.assertEqual(stock.quantite, Decimal("2"))
        self.assertEqual(stock.quantite_kg, Decimal("50"))
        # pps désormais verrouillé sur 25 → conversion suivante à 50 refusée
        self.assertEqual(produit_neutre.poids_par_sac, Decimal("25"))
        with self.assertRaises(ErreurStock):
            convertir_kg_en_sac(stock, nombre_sacs=1, poids_par_sac=Decimal("50"), updated_by=self.user)

    # ── Scénario 5 : deux produits distincts = deux lignes, conversions exactes ─
    def test_deux_produits_poids_differents_conversions_exactes_et_isolees(self):
        from inventaire.services import convertir_sac_en_kg
        stock_25 = Stock.objects.create(
            produit=self.produit_25, lieu=self.lieu_boutique,
            quantite=Decimal("10"), quantite_kg=Decimal("0"),
        )
        stock_50 = Stock.objects.create(
            produit=self.produit_50, lieu=self.lieu_boutique,
            quantite=Decimal("5"), quantite_kg=Decimal("0"),
        )
        # 10 sacs × 25 kg = 250 kg exact
        kg_25 = convertir_sac_en_kg(stock_25, 10, updated_by=self.user, idempotency_key="iso-25")
        self.assertEqual(kg_25, Decimal("250"))
        stock_25.refresh_from_db()
        self.assertEqual(stock_25.quantite, Decimal("0"))
        self.assertEqual(stock_25.quantite_kg, Decimal("250"))

        # 5 sacs × 50 kg = 250 kg exact
        kg_50 = convertir_sac_en_kg(stock_50, 5, updated_by=self.user, idempotency_key="iso-50")
        self.assertEqual(kg_50, Decimal("250"))
        stock_50.refresh_from_db()
        self.assertEqual(stock_50.quantite, Decimal("0"))
        self.assertEqual(stock_50.quantite_kg, Decimal("250"))

        # Les deux entrées restent séparées — aucune fusion
        self.assertNotEqual(stock_25.pk, stock_50.pk)

    # ── Scénario 6 : batch refuse mélange pps ─────────────────────────────────
    def test_batch_achat_refuse_melange_pps(self):
        from inventaire.services import enregistrer_achats_mpsl_batch
        p_batch = Produit.objects.create(
            categorie=self.cat, nom="Maïs batch melange", code="MBM02",
            unite="sac", entreprise=self.entreprise, poids_par_sac=Decimal("25"),
        )
        Stock.objects.create(
            produit=p_batch, lieu=self.lieu_mpsl,
            quantite=Decimal("8"), quantite_kg=Decimal("0"),
        )
        with self.assertRaises(ErreurStock) as cm:
            enregistrer_achats_mpsl_batch(
                self.lieu_mpsl,
                [{"produit_nom": "Maïs batch melange", "quantite": 3,
                  "unite": "sacs", "poids_par_sac": Decimal("50"), "prix_unitaire": 0}],
                created_by=self.user,
            )
        self.assertIn("Mélange", str(cm.exception))
