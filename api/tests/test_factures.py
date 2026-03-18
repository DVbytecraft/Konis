from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from produits.models import Categorie, Produit
from ventes.models import Facture, LigneFacture


class FacturesApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        entreprise_b = Entreprise.objects.create(nom="KONIS-B")
        cls.shop = Lieu.objects.create(entreprise=entreprise, nom="Boutique A", code="BTA", type_lieu=Lieu.TYPE_MAGASIN)
        cls.shop2 = Lieu.objects.create(entreprise=entreprise, nom="Boutique B", code="BTB", type_lieu=Lieu.TYPE_MAGASIN)
        cls.factory = Lieu.objects.create(entreprise=entreprise, nom="Usine A", code="USA", type_lieu=Lieu.TYPE_USINE)
        cls.shop_b = Lieu.objects.create(entreprise=entreprise_b, nom="Boutique X", code="BTX", type_lieu=Lieu.TYPE_MAGASIN)

        cls.admin = CustomUser.objects.create_user(
            username="admin_fact",
            password="admin123456",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable_fact",
            password="compte123456",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        cls.boutique = CustomUser.objects.create_user(
            username="boutique_fact",
            password="boutique123456",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.shop,
        )
        cls.usine = CustomUser.objects.create_user(
            username="usine_fact",
            password="usine123456",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=cls.factory,
        )
        cat = Categorie.objects.create(nom="Cat test", entreprise=entreprise)
        cls.produit = Produit.objects.create(categorie=cat, nom="Produit test facture", code="FACT-001", unite="piece", entreprise=entreprise)

    def _auth_headers(self, user):
        refresh = RefreshToken.for_user(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {str(refresh.access_token)}"}

    def test_boutique_create_facture_forces_user_lieu(self):
        url = reverse("factures-list-create")
        payload = {
            "lieu": self.shop2.id,
            "client_nom": "Client test",
            "lignes": [{"produit": self.produit.id, "description": "Ligne test", "quantite": "2", "prix_unitaire": "100"}],
        }
        r = self.client.post(url, payload, format="json", **self._auth_headers(self.boutique))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        facture = Facture.objects.get(pk=r.json()["id"])
        self.assertEqual(facture.lieu_id, self.shop.id)
        self.assertEqual(facture.source_role, CustomUser.ROLE_BOUTIQUE)

    def test_comptable_create_requires_lieu(self):
        url = reverse("factures-list-create")
        payload = {
            "client_nom": "Client test",
            "lignes": [{"description": "Service", "quantite": "1", "prix_unitaire": "2500"}],
        }
        r = self.client.post(url, payload, format="json", **self._auth_headers(self.comptable))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_comptable_can_create_with_lieu(self):
        url = reverse("factures-list-create")
        payload = {
            "lieu": self.shop.id,
            "client_nom": "Client compta",
            "lignes": [{"description": "Service comptable", "quantite": "1", "prix_unitaire": "2500"}],
        }
        r = self.client.post(url, payload, format="json", **self._auth_headers(self.comptable))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        self.assertEqual(Decimal(str(r.json()["total"])), Decimal("2500"))

    def test_boutique_list_only_own_factures(self):
        f1 = Facture.objects.create(
            lieu=self.shop,
            numero="INV-BTA-20260101-000001",
            source_role=CustomUser.ROLE_ADMIN,
            total=Decimal("100"),
        )
        LigneFacture.objects.create(facture=f1, description="A", quantite=1, prix_unitaire=100)
        f2 = Facture.objects.create(
            lieu=self.shop2,
            numero="INV-BTB-20260101-000001",
            source_role=CustomUser.ROLE_ADMIN,
            total=Decimal("200"),
        )
        LigneFacture.objects.create(facture=f2, description="B", quantite=1, prix_unitaire=200)

        r = self.client.get(reverse("factures-list-create"), **self._auth_headers(self.boutique))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["lieu"], self.shop.id)

    def test_admin_list_all_factures(self):
        Facture.objects.create(
            lieu=self.shop,
            numero="INV-BTA-20260101-000010",
            source_role=CustomUser.ROLE_ADMIN,
            total=Decimal("100"),
        )
        Facture.objects.create(
            lieu=self.factory,
            numero="INV-USA-20260101-000011",
            source_role=CustomUser.ROLE_USINE,
            total=Decimal("300"),
        )
        r = self.client.get(reverse("factures-list-create"), **self._auth_headers(self.admin))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertGreaterEqual(len(items), 2)

    def test_comptable_cannot_access_other_entreprise_factures(self):
        facture_other = Facture.objects.create(
            lieu=self.shop_b,
            numero="INV-BTX-20260101-000001",
            source_role=CustomUser.ROLE_ADMIN,
            total=Decimal("999"),
        )
        LigneFacture.objects.create(facture=facture_other, description="Ext", quantite=1, prix_unitaire=999)

        r_list = self.client.get(reverse("factures-list-create"), **self._auth_headers(self.comptable))
        self.assertEqual(r_list.status_code, status.HTTP_200_OK)
        data = r_list.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertTrue(all(item["lieu"] != self.shop_b.id for item in items))

        r_detail = self.client.get(
            reverse("factures-detail", kwargs={"pk": facture_other.id}),
            **self._auth_headers(self.comptable),
        )
        self.assertEqual(r_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_comptable_routes_are_read_only(self):
        r = self.client.post(
            reverse("comptable-ventes-list"),
            {"foo": "bar"},
            format="json",
            **self._auth_headers(self.comptable),
        )
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
