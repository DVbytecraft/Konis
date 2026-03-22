from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Produit
from ventes.models import Ticket


class MoutureEndpointsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(nom="KONIS")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.entreprise,
            nom="Boutique A",
            type_lieu=Lieu.TYPE_MAGASIN,
            mouture_enabled=True,
        )
        cls.usine = Lieu.objects.create(
            entreprise=cls.entreprise,
            nom="Usine A",
            type_lieu=Lieu.TYPE_USINE,
            mouture_enabled=True,
        )
        cls.boutique_user = CustomUser.objects.create_user(
            username="boutique",
            password="boutique123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=cls.entreprise,
            lieu=cls.boutique,
        )
        cls.usine_user = CustomUser.objects.create_user(
            username="usine",
            password="usine123",
            role=CustomUser.ROLE_USINE,
            entreprise=cls.entreprise,
            lieu=cls.usine,
        )
        cls.comptable_user = CustomUser.objects.create_user(
            username="comptable",
            password="comptable123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=cls.entreprise,
        )
        # poids_par_sac=50 : 1 sac = 50 kg (used for sac-unit tests)
        cls.produit = Produit.objects.create(
            nom="Mais",
            code="MAIS",
            unite="kg",
            entreprise=cls.entreprise,
            poids_par_sac=Decimal("50.000"),
        )
        Stock.objects.create(produit=cls.produit, lieu=cls.boutique, quantite=100)

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    # ──────────────────────────────────────────────────────────────────────────
    # Contrôle d'accès
    # ──────────────────────────────────────────────────────────────────────────

    def test_boutique_mouture_refuse_comptable(self):
        response = self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite_apportee": "10", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "50"},
            format="json",
            **self._auth(self.comptable_user),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usine_mouture_refuse_boutique(self):
        response = self.client.post(
            "/api/factory/mouture-seule/",
            {"quantite_apportee": "10", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "50"},
            format="json",
            **self._auth(self.boutique_user),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ──────────────────────────────────────────────────────────────────────────
    # Idempotence
    # ──────────────────────────────────────────────────────────────────────────

    def test_boutique_mouture_idempotente(self):
        payload = {
            "quantite_apportee": "10",
            "quantite_achetee": "0",
            "unite": "kg",
            "prix_par_kg": "50",
            "produit_nom": "Mais",
        }
        h = {"HTTP_IDEMPOTENCY_KEY": "boutique-key-1"}
        r1 = self.client.post(
            "/api/boutique/mouture-seule/", payload, format="json",
            **self._auth(self.boutique_user), **h,
        )
        r2 = self.client.post(
            "/api/boutique/mouture-seule/", payload, format="json",
            **self._auth(self.boutique_user), **h,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.json())
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.json())
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            Ticket.objects.filter(lieu=self.boutique, idempotency_key="boutique-key-1").count(),
            1,
        )

    def test_usine_mouture_idempotente(self):
        payload = {
            "quantite_apportee": "2",
            "quantite_achetee": "0",
            "unite": "kg",
            "prix_par_kg": "250",
        }
        h = {"HTTP_IDEMPOTENCY_KEY": "usine-key-1"}
        r1 = self.client.post(
            "/api/factory/mouture-seule/", payload, format="json",
            **self._auth(self.usine_user), **h,
        )
        r2 = self.client.post(
            "/api/factory/mouture-seule/", payload, format="json",
            **self._auth(self.usine_user), **h,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.json())
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.json())
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            Ticket.objects.filter(lieu=self.usine, idempotency_key="usine-key-1").count(),
            1,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Calcul mouture-seule — unité kg
    # ──────────────────────────────────────────────────────────────────────────

    def test_boutique_mouture_seule_calcul_kg(self):
        """10 kg apportés @ 50 FCFA/kg → coût mouture = 500 FCFA."""
        r = self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite_apportee": "10", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "50"},
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-calcul-kg-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        self.assertEqual(Decimal(data["cout_mouture"]), Decimal("500.00"))
        self.assertEqual(Decimal(data["montant_total"]), Decimal("500.00"))

    def test_boutique_mouture_seule_calcul_mixte_apportee_achetee(self):
        """5 kg apportés + 3 kg achetés → 8 kg total @ 100/kg → coût = 800."""
        r = self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite_apportee": "5", "quantite_achetee": "3", "unite": "kg", "prix_par_kg": "100"},
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-calcul-mixte-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        self.assertEqual(Decimal(data["cout_mouture"]), Decimal("800.00"))
        # quantite_apportee_client doit être sauvegardée en kg
        self.assertEqual(Decimal(data["quantite_apportee_client"]), Decimal("5.000"))

    # ──────────────────────────────────────────────────────────────────────────
    # Calcul mouture-seule — unité sac (conversion via poids_par_sac)
    # ──────────────────────────────────────────────────────────────────────────

    def test_boutique_mouture_seule_sac_conversion(self):
        """2 sacs apportés × 50 kg/sac @ 250 FCFA/kg → 100 kg × 250 = 25 000 FCFA."""
        r = self.client.post(
            "/api/boutique/mouture-seule/",
            {
                "quantite_apportee": "2",
                "quantite_achetee": "0",
                "unite": "sac",
                "prix_par_kg": "250",
                "produit_id": self.produit.id,
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-sac-conversion-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        self.assertEqual(Decimal(data["cout_mouture"]), Decimal("25000.00"))
        # Quantité apportée normalisée en kg : 2 × 50 = 100
        self.assertEqual(Decimal(data["quantite_apportee_client"]), Decimal("100.000"))

    def test_boutique_mouture_seule_sac_sans_produit_id_erreur(self):
        """unité sac sans produit_id → 400 (poids_par_sac inconnu)."""
        r = self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite_apportee": "2", "quantite_achetee": "0", "unite": "sac", "prix_par_kg": "250"},
            format="json",
            **self._auth(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_boutique_mouture_seule_zero_quantite_erreur(self):
        """quantite_apportee=0 et quantite_achetee=0 → 400."""
        r = self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite_apportee": "0", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "50"},
            format="json",
            **self._auth(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ──────────────────────────────────────────────────────────────────────────
    # Vente + mouture (mouture auto-calculée sur grain acheté)
    # ──────────────────────────────────────────────────────────────────────────

    def test_vente_avec_mouture_calcul_grain_achete(self):
        """Vente 2 kg + mouture : grain acheté = somme des lignes en kg @ 75/kg."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.id, "quantite": "2", "prix_unitaire": "500"}],
                "mouture": True,
                "prix_mouture_kg": "75",
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="vente-mouture-grain-achete-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        self.assertTrue(data["mouture"])
        # 2 kg × 75 = 150 coût mouture ; total = 1000 + 150 = 1150
        self.assertEqual(Decimal(data["cout_mouture"]), Decimal("150.00"))
        self.assertEqual(Decimal(data["montant_total"]), Decimal("1150.00"))

    def test_vente_avec_mouture_et_grain_apporte(self):
        """Scénario mixte : achat 2 kg + 3 kg apportés → total moudre 5 kg @ 80/kg → 400."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.id, "quantite": "2", "prix_unitaire": "500"}],
                "mouture": True,
                "prix_mouture_kg": "80",
                "quantite_apportee_mouture": "3",
                "unite_apportee_mouture": "kg",
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="vente-mouture-grain-apporte-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        # Grain acheté = 2 kg, apporté = 3 kg → total 5 kg × 80 = 400
        self.assertEqual(Decimal(data["cout_mouture"]), Decimal("400.00"))
        # total = produits (1000) + mouture (400) = 1400
        self.assertEqual(Decimal(data["montant_total"]), Decimal("1400.00"))
        # quantite_apportee_client sauvegardée
        self.assertEqual(Decimal(data["quantite_apportee_client"]), Decimal("3.000"))

    def test_vente_avec_mouture_grain_apporte_sac(self):
        """Grain apporté en sac : 1 sac × 50 kg/sac + 2 kg achetés → 52 kg @ 60/kg → 3120."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.id, "quantite": "2", "prix_unitaire": "500"}],
                "mouture": True,
                "prix_mouture_kg": "60",
                "quantite_apportee_mouture": "1",
                "unite_apportee_mouture": "sac",
                "produit_id_apportee": self.produit.id,
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="vente-mouture-grain-sac-001",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        # 1 sac = 50 kg + 2 kg achetés = 52 kg × 60 = 3120
        self.assertEqual(Decimal(data["cout_mouture"]), Decimal("3120.00"))
        self.assertEqual(Decimal(data["quantite_apportee_client"]), Decimal("50.000"))

    # ──────────────────────────────────────────────────────────────────────────
    # Historique
    # ──────────────────────────────────────────────────────────────────────────

    def test_boutique_mouture_history_get(self):
        self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite_apportee": "10", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "50"},
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-history-setup-1",
        )
        self.client.post(
            "/api/boutique/mouture-seule/",
            {
                "quantite_apportee": "4",
                "quantite_achetee": "0",
                "unite": "sac",
                "prix_par_kg": "200",
                "produit_id": self.produit.id,
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-history-setup-2",
        )
        response = self.client.get("/api/boutique/mouture-seule/", **self._auth(self.boutique_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        body = response.json()
        self.assertIn("results", body)
        self.assertGreaterEqual(len(body["results"]), 2)

    def test_boutique_mouture_history_inclut_mouture_seule_et_vente(self):
        self.client.post(
            "/api/boutique/mouture-seule/",
            {
                "quantite_apportee": "3",
                "quantite_achetee": "0",
                "unite": "kg",
                "prix_par_kg": "100",
                "produit_nom": "Mil",
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-history-inclut-seule-001",
        )
        vente = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.id, "quantite": "2", "prix_unitaire": "500"}],
                "mouture": True,
                "prix_mouture_kg": "75",
            },
            format="json",
            **self._auth(self.boutique_user),
            HTTP_IDEMPOTENCY_KEY="mouture-history-inclut-vente-001",
        )
        self.assertEqual(vente.status_code, status.HTTP_201_CREATED, vente.json())

        response = self.client.get("/api/boutique/mouture-seule/", **self._auth(self.boutique_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        results = response.json()["results"]
        sources = {item.get("mouture_source") for item in results}
        self.assertIn("mouture_seule", sources)
        self.assertIn("vente_avec_mouture", sources)

        seule = self.client.get(
            "/api/boutique/mouture-seule/?source=seule", **self._auth(self.boutique_user)
        )
        self.assertEqual(seule.status_code, status.HTTP_200_OK, seule.json())
        self.assertTrue(
            all(item.get("mouture_source") == "mouture_seule" for item in seule.json()["results"])
        )

        vente_only = self.client.get(
            "/api/boutique/mouture-seule/?source=vente", **self._auth(self.boutique_user)
        )
        self.assertEqual(vente_only.status_code, status.HTTP_200_OK, vente_only.json())
        self.assertTrue(
            all(
                item.get("mouture_source") == "vente_avec_mouture"
                for item in vente_only.json()["results"]
            )
        )
