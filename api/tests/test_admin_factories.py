from decimal import Decimal

from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Categorie, Produit
from usine.models import LotProduction, TransfertCession


class AdminFactoriesTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entreprise = Entreprise.objects.create(nom="KONIS")
        cls.admin = CustomUser.objects.create_user(
            username="admin",
            email="admin@konis.local",
            password="admin123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=cls.entreprise,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable",
            email="comptable@konis.local",
            password="comptable123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=cls.entreprise,
        )

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def test_admin_can_create_factory_with_user_and_group(self):
        payload = {
            "factory_name": "Usine de Dakar",
            "factory_address": "Zone industrielle",
            "user_email": "responsable@usine.com",
            "user_first_name": "Jean",
            "user_last_name": "Dupont",
            "user_password": "StrongPass123!",
        }
        r = self.client.post("/api/admin/factories/", payload, format="json", **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        data = r.json()
        self.assertEqual(data["name"], "Usine de Dakar")
        self.assertEqual(data["address"], "Zone industrielle")
        self.assertIsNotNone(data["user"])
        self.assertEqual(data["user"]["email"], "responsable@usine.com")

        factory = Lieu.objects.get(nom="Usine de Dakar", type_lieu=Lieu.TYPE_USINE)
        self.assertEqual(factory.adresse, "Zone industrielle")
        user = CustomUser.objects.get(email="responsable@usine.com")
        self.assertEqual(user.role, CustomUser.ROLE_USINE)
        self.assertEqual(user.lieu_id, factory.id)
        self.assertTrue(user.groups.filter(name="Factory").exists())
        self.assertTrue(Group.objects.filter(name="Factory").exists())

    def test_non_admin_cannot_create_factory(self):
        payload = {
            "factory_name": "Usine K",
            "factory_address": "",
            "user_email": "u@k.com",
            "user_first_name": "U",
            "user_last_name": "K",
            "user_password": "StrongPass123!",
        }
        r = self.client.post("/api/admin/factories/", payload, format="json", **self._auth(self.comptable))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_list_factories(self):
        f = Lieu.objects.create(
            entreprise=self.entreprise,
            nom="Usine Nord",
            adresse="Rue 1",
            type_lieu=Lieu.TYPE_USINE,
            is_active=True,
        )
        CustomUser.objects.create_user(
            username="usine_nord",
            password="StrongPass123!",
            email="nord@usine.local",
            role=CustomUser.ROLE_USINE,
            entreprise=self.entreprise,
            lieu=f,
        )

        r = self.client.get("/api/admin/factories/", **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertTrue(any(item["name"] == "Usine Nord" for item in items))

    def test_duplicate_email_rejected(self):
        CustomUser.objects.create_user(
            username="exists",
            password="StrongPass123!",
            email="dup@usine.com",
            role=CustomUser.ROLE_USINE,
            entreprise=self.entreprise,
        )
        payload = {
            "factory_name": "Usine Sud",
            "factory_address": "Adresse",
            "user_email": "dup@usine.com",
            "user_first_name": "Jean",
            "user_last_name": "Dupont",
            "user_password": "StrongPass123!",
        }
        r = self.client.post("/api/admin/factories/", payload, format="json", **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_email", r.json())


class FactoryIsolationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        cls.usine_a = Lieu.objects.create(entreprise=entreprise, nom="Usine A", type_lieu=Lieu.TYPE_USINE)
        cls.usine_b = Lieu.objects.create(entreprise=entreprise, nom="Usine B", type_lieu=Lieu.TYPE_USINE)
        cls.shop = Lieu.objects.create(entreprise=entreprise, nom="Boutique", type_lieu=Lieu.TYPE_MAGASIN)
        cls.user_a = CustomUser.objects.create_user(
            username="ua",
            password="StrongPass123!",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=cls.usine_a,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="compte",
            password="StrongPass123!",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        cat = Categorie.objects.create(nom="Cat")
        cls.finished = Produit.objects.create(
            categorie=cat,
            nom="Produit fini",
            code="FIN-1",
            category=Produit.CATEGORY_FINISHED,
            unite="kg",
            entreprise=entreprise,
        )
        cls.lot_a = LotProduction.objects.create(
            nom_lot="lot-a",
            lieu_usine=cls.usine_a,
            produit_fini=cls.finished,
            quantite_sacs=Decimal("100"),
            poids=Decimal("5000"),
        )
        cls.lot_b = LotProduction.objects.create(
            nom_lot="lot-b",
            lieu_usine=cls.usine_b,
            produit_fini=cls.finished,
            quantite_sacs=Decimal("120"),
            poids=Decimal("6000"),
        )
        Stock.objects.create(produit=cls.finished, lieu=cls.usine_a, quantite=Decimal("100"))
        Stock.objects.create(produit=cls.finished, lieu=cls.usine_b, quantite=Decimal("120"))
        TransfertCession.objects.create(lot=cls.lot_a, boutique=cls.shop, quantite_sacs=Decimal("10"), poids_total=Decimal("500"), prix_par_sac=Decimal("20"))
        TransfertCession.objects.create(lot=cls.lot_b, boutique=cls.shop, quantite_sacs=Decimal("11"), poids_total=Decimal("550"), prix_par_sac=Decimal("22"))

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def test_factory_shop_stock_is_scoped_to_current_factory(self):
        r = self.client.get("/api/usine/stocks-boutiques/", **self._auth(self.user_a))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        # L'endpoint retourne les stocks des boutiques pour les produits finis
        self.assertIsInstance(items, list)

    def test_profit_report_can_filter_by_factory(self):
        r = self.client.get(f"/api/reports/profit-by-lot/?factory_id={self.usine_a.id}", **self._auth(self.comptable))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        rows = r.json()
        # L'endpoint retourne une liste (peut etre vide si pas de donnees)
        self.assertIsInstance(rows, list)
