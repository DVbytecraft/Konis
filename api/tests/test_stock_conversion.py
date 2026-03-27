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
