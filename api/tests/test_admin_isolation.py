from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from depenses.models import CategorieDepense
from produits.models import Categorie, Produit


class AdminIsolationTests(APITestCase):
    """Tests IDOR admin : un admin ne doit pas accéder à une autre entreprise."""

    @classmethod
    def setUpTestData(cls):
        cls.ent_a = Entreprise.objects.create(nom="Entreprise A")
        cls.ent_b = Entreprise.objects.create(nom="Entreprise B")

        cls.usine_a = Lieu.objects.create(entreprise=cls.ent_a, nom="Usine A", type_lieu=Lieu.TYPE_USINE)
        cls.usine_b = Lieu.objects.create(entreprise=cls.ent_b, nom="Usine B", type_lieu=Lieu.TYPE_USINE)
        cls.shop_a = Lieu.objects.create(entreprise=cls.ent_a, nom="Boutique A", type_lieu=Lieu.TYPE_MAGASIN)
        cls.shop_b = Lieu.objects.create(entreprise=cls.ent_b, nom="Boutique B", type_lieu=Lieu.TYPE_MAGASIN)

        cls.admin_a = CustomUser.objects.create_user(
            username="admin_a",
            password="pass",
            role=CustomUser.ROLE_ADMIN,
            entreprise=cls.ent_a,
        )

        cls.cat_a = Categorie.objects.create(nom="Cat A", entreprise=cls.ent_a)
        cls.cat_b = Categorie.objects.create(nom="Cat B", entreprise=cls.ent_b)
        cls.dep_cat_a = CategorieDepense.objects.create(nom="Divers A", entreprise=cls.ent_a)
        cls.dep_cat_b = CategorieDepense.objects.create(nom="Divers B", entreprise=cls.ent_b)
        cls.produit_b = Produit.objects.create(
            categorie=cls.cat_b,
            nom="Produit B",
            code="PB001",
            category=Produit.CATEGORY_FINISHED,
            unite="kg",
            entreprise=cls.ent_b,
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_admin_cannot_list_boutique_stock_other_entreprise(self):
        r = self.client.get(
            f"/api/boutique/stock/?lieu={self.shop_b.id}",
            **self._auth(self.admin_a),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(items, [], "Admin A ne doit pas voir le stock d'une autre entreprise")

    def test_admin_categories_scoped_to_entreprise(self):
        r = self.client.get("/api/admin/categories/", **self._auth(self.admin_a))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        ids = [c["id"] for c in items]
        self.assertIn(self.cat_a.id, ids)
        self.assertNotIn(self.cat_b.id, ids)

    def test_admin_depense_categories_scoped_to_entreprise(self):
        r = self.client.get("/api/admin/categories-depense/", **self._auth(self.admin_a))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        ids = [c["id"] for c in items]
        self.assertIn(self.dep_cat_a.id, ids)
        self.assertNotIn(self.dep_cat_b.id, ids)

    def test_admin_cannot_create_achat_usine_other_entreprise(self):
        payload = {
            "lieu": self.usine_b.id,
            "produit_nom": "Mais",
            "quantite": "10",
            "unite": "kg",
            "prix_unitaire": "100",
        }
        r = self.client.post("/api/usine/achats/", payload, format="json", **self._auth(self.admin_a))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_create_lot_other_entreprise(self):
        payload = {
            "nom_lot": "lot-b",
            "lieu_usine": self.usine_b.id,
            "produit_fini": self.produit_b.id,
            "quantite_sacs": "5",
            "poids": "250",
            "unite_poids": "kg",
        }
        r = self.client.post("/api/usine/lots/", payload, format="json", **self._auth(self.admin_a))
        # Le serializer rejette avec 400 (validation cross-tenant) avant d'atteindre 403
        self.assertIn(r.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

    def test_admin_cannot_create_facture_other_entreprise(self):
        payload = {
            "lieu": self.shop_b.id,
            "client_nom": "Client B",
            "lignes": [{"description": "Service", "quantite": "1", "prix_unitaire": "1000"}],
        }
        r = self.client.post("/api/factures/", payload, format="json", **self._auth(self.admin_a))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
