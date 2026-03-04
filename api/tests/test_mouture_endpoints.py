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
        entreprise = Entreprise.objects.create(nom="KONIS")
        cls.boutique = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique A",
            type_lieu=Lieu.TYPE_MAGASIN,
            mouture_enabled=True,
        )
        cls.usine = Lieu.objects.create(
            entreprise=entreprise,
            nom="Usine A",
            type_lieu=Lieu.TYPE_USINE,
            mouture_enabled=True,
        )
        cls.boutique_user = CustomUser.objects.create_user(
            username="boutique",
            password="boutique123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.boutique,
        )
        cls.usine_user = CustomUser.objects.create_user(
            username="usine",
            password="usine123",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=cls.usine,
        )
        cls.comptable_user = CustomUser.objects.create_user(
            username="comptable",
            password="comptable123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        cls.produit = Produit.objects.create(nom="Mais", code="MAIS", unite="kg", entreprise=entreprise)
        Stock.objects.create(produit=cls.produit, lieu=cls.boutique, quantite=100)

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def test_boutique_mouture_refuse_comptable(self):
        response = self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite": "10", "unite": "kg", "prix_unitaire": "50"},
            format="json",
            **self._auth(self.comptable_user),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usine_mouture_refuse_boutique(self):
        response = self.client.post(
            "/api/factory/mouture-seule/",
            {"quantite": "10", "unite": "kg", "prix_unitaire": "50"},
            format="json",
            **self._auth(self.boutique_user),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_boutique_mouture_idempotente(self):
        payload = {"quantite": "10", "unite": "kg", "prix_unitaire": "50", "produit_nom": "Mais"}
        h = {"HTTP_IDEMPOTENCY_KEY": "boutique-key-1"}
        r1 = self.client.post(
            "/api/boutique/mouture-seule/",
            payload,
            format="json",
            **self._auth(self.boutique_user),
            **h,
        )
        r2 = self.client.post(
            "/api/boutique/mouture-seule/",
            payload,
            format="json",
            **self._auth(self.boutique_user),
            **h,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.json())
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.json())
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            Ticket.objects.filter(lieu=self.boutique, idempotency_key="boutique-key-1").count(),
            1,
        )

    def test_usine_mouture_idempotente(self):
        payload = {"quantite": "2", "unite": "sac", "prix_unitaire": "250"}
        h = {"HTTP_IDEMPOTENCY_KEY": "usine-key-1"}
        r1 = self.client.post(
            "/api/factory/mouture-seule/",
            payload,
            format="json",
            **self._auth(self.usine_user),
            **h,
        )
        r2 = self.client.post(
            "/api/factory/mouture-seule/",
            payload,
            format="json",
            **self._auth(self.usine_user),
            **h,
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.json())
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.json())
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            Ticket.objects.filter(lieu=self.usine, idempotency_key="usine-key-1").count(),
            1,
        )

    def test_boutique_mouture_history_get(self):
        self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite": "10", "unite": "kg", "prix_unitaire": "50"},
            format="json",
            **self._auth(self.boutique_user),
        )
        self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite": "4", "unite": "sac", "prix_unitaire": "200"},
            format="json",
            **self._auth(self.boutique_user),
        )
        response = self.client.get("/api/boutique/mouture-seule/", **self._auth(self.boutique_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        body = response.json()
        self.assertIn("results", body)
        self.assertGreaterEqual(len(body["results"]), 2)

    def test_boutique_mouture_history_inclut_mouture_seule_et_vente(self):
        self.client.post(
            "/api/boutique/mouture-seule/",
            {"quantite": "3", "unite": "kg", "prix_unitaire": "100", "produit_nom": "Mil"},
            format="json",
            **self._auth(self.boutique_user),
        )
        vente = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [
                    {"produit": self.produit.id, "quantite": "2", "prix_unitaire": "500"},
                ],
                "mouture": True,
                "prix_mouture_kg": "75",
            },
            format="json",
            **self._auth(self.boutique_user),
        )
        self.assertEqual(vente.status_code, status.HTTP_201_CREATED, vente.json())

        response = self.client.get("/api/boutique/mouture-seule/", **self._auth(self.boutique_user))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        results = response.json()["results"]
        sources = {item.get("mouture_source") for item in results}
        self.assertIn("mouture_seule", sources)
        self.assertIn("vente_avec_mouture", sources)

        seule = self.client.get("/api/boutique/mouture-seule/?source=seule", **self._auth(self.boutique_user))
        self.assertEqual(seule.status_code, status.HTTP_200_OK, seule.json())
        self.assertTrue(all(item.get("mouture_source") == "mouture_seule" for item in seule.json()["results"]))

        vente_only = self.client.get("/api/boutique/mouture-seule/?source=vente", **self._auth(self.boutique_user))
        self.assertEqual(vente_only.status_code, status.HTTP_200_OK, vente_only.json())
        self.assertTrue(all(item.get("mouture_source") == "vente_avec_mouture" for item in vente_only.json()["results"]))
