from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Categorie, Produit
from usine.models import LotProduction


class UsineModuleTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        entreprise_b = Entreprise.objects.create(nom="KONIS-B")
        cls.usine = Lieu.objects.create(entreprise=entreprise, nom="Usine", type_lieu=Lieu.TYPE_USINE)
        cls.boutique = Lieu.objects.create(entreprise=entreprise, nom="Boutique", type_lieu=Lieu.TYPE_MAGASIN)
        cls.usine_b = Lieu.objects.create(entreprise=entreprise_b, nom="Usine B", type_lieu=Lieu.TYPE_USINE)
        cls.boutique_b = Lieu.objects.create(entreprise=entreprise_b, nom="Boutique B", type_lieu=Lieu.TYPE_MAGASIN)
        cls.admin = CustomUser.objects.create_user(
            username="admin",
            password="admin123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
        )
        cls.user_usine = CustomUser.objects.create_user(
            username="usine",
            password="usine123",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=cls.usine,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="compta",
            password="compta123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        cat = Categorie.objects.create(nom="Cat", entreprise=entreprise)
        cls.mp = Produit.objects.create(
            categorie=cat,
            nom="Maïs",
            code="MP001",
            category=Produit.CATEGORY_RAW_MATERIAL,
            unite="kg",
            entreprise=entreprise,
        )
        cls.finished = Produit.objects.create(
            categorie=cat,
            nom="Aliment fini",
            code="PF001",
            category=Produit.CATEGORY_FINISHED,
            unite="kg",
            entreprise=entreprise,
        )
        Stock.objects.create(produit=cls.mp, lieu=cls.usine, quantite=Decimal("100"))

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def test_locations_by_type_filters(self):
        url = "/api/locations/by-type/?type=factory"
        r = self.client.get(url, **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(r.json()), 1)
        self.assertTrue(all(item["type_lieu"] == Lieu.TYPE_USINE for item in r.json()))

    def test_factory_user_can_fetch_shop_locations_by_type(self):
        url = "/api/locations/by-type/?type=shop"
        r = self.client.get(url, **self._auth(self.user_usine))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["type_lieu"] == Lieu.TYPE_MAGASIN for item in r.json()))

    def test_usine_create_lot_adds_finished_stock(self):
        """Test que la creation d'un lot ajoute le stock produit fini a l'usine."""
        payload = {
            "nom_lot": "anitche01",
            "lieu_usine": self.usine.id,
            "produit_fini": self.finished.id,
            "quantite_sacs": "30.00",
            "poids": "1500",
            "unite_poids": "kg",
        }
        r = self.client.post("/api/usine/lots/", payload, format="json", **self._auth(self.user_usine))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

        stock_pf = Stock.objects.get(produit=self.finished, lieu=self.usine)
        self.assertEqual(stock_pf.quantite, Decimal("30"))

    def test_usine_cession_and_benefice_report(self):
        lot = LotProduction.objects.create(
            nom_lot="anitche02",
            lieu_usine=self.usine,
            produit_fini=self.finished,
            quantite_sacs=Decimal("10"),
            poids=Decimal("500"),
        )
        Stock.objects.update_or_create(
            produit=self.finished,
            lieu=self.usine,
            defaults={"quantite": Decimal("10")},
        )

        cession_payload = {
            "lot": lot.id,
            "boutique": self.boutique.id,
            "quantite_sacs": "4.00",
            "poids_total": "200",
            "prix_par_sac": "20.00",
        }
        rc = self.client.post("/api/usine/cessions/", cession_payload, format="json", **self._auth(self.user_usine))
        self.assertEqual(rc.status_code, status.HTTP_201_CREATED, rc.json())

        rr = self.client.get("/api/usine/rapports/benefices/", **self._auth(self.comptable))
        self.assertEqual(rr.status_code, status.HTTP_200_OK)
        data = rr.json()
        self.assertTrue(any(item["nom_lot"] == "anitche02" for item in data))

    def test_admin_user_role_usine_requires_usine_lieu(self):
        payload = {
            "username": "badusine",
            "password": "x123456",
            "role": CustomUser.ROLE_USINE,
            "entreprise": self.usine.entreprise_id,
            "lieu": self.boutique.id,
        }
        r = self.client.post("/api/admin/users/", payload, format="json", **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lieu", r.json())

    def test_admin_can_access_factory_endpoints(self):
        """Test que l'admin peut acceder aux endpoints usine."""
        r = self.client.get("/api/factory/dashboard/?lieu=" + str(self.usine.id), **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_admin_can_create_lot_with_lieu_param(self):
        """Test que l'admin peut creer un lot en specifiant le lieu."""
        payload = {
            "nom_lot": "admin-lot-01",
            "lieu_usine": self.usine.id,
            "produit_fini": self.finished.id,
            "quantite_sacs": "50.00",
            "poids": "2500",
            "unite_poids": "kg",
        }
        r = self.client.post("/api/usine/lots/", payload, format="json", **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

        stock_pf = Stock.objects.get(produit=self.finished, lieu=self.usine)
        self.assertEqual(stock_pf.quantite, Decimal("50"))

    def test_comptable_profit_reports_are_scoped_to_entreprise(self):
        # Donnees dans l'entreprise du comptable
        lot_local = LotProduction.objects.create(
            nom_lot="lot-local",
            lieu_usine=self.usine,
            produit_fini=self.finished,
            quantite_sacs=Decimal("10"),
            poids=Decimal("500"),
        )
        Stock.objects.update_or_create(produit=self.finished, lieu=self.usine, defaults={"quantite": Decimal("10")})
        self.client.post(
            "/api/usine/cessions/",
            {"lot": lot_local.id, "boutique": self.boutique.id, "quantite_sacs": "2", "poids_total": "100", "prix_par_sac": "20"},
            format="json",
            **self._auth(self.user_usine),
        )

        # Donnees dans une autre entreprise
        lot_ext = LotProduction.objects.create(
            nom_lot="lot-externe",
            lieu_usine=self.usine_b,
            produit_fini=self.finished,
            quantite_sacs=Decimal("10"),
            poids=Decimal("500"),
        )
        Stock.objects.update_or_create(produit=self.finished, lieu=self.usine_b, defaults={"quantite": Decimal("10")})
        self.client.post(
            "/api/usine/cessions/",
            {"lot": lot_ext.id, "boutique": self.boutique_b.id, "quantite_sacs": "2", "poids_total": "100", "prix_par_sac": "20"},
            format="json",
            **self._auth(self.admin),
        )

        r_lot = self.client.get("/api/reports/profit-by-lot/", **self._auth(self.comptable))
        self.assertEqual(r_lot.status_code, status.HTTP_200_OK)
        lots = r_lot.json()
        noms = {item["nom_lot"] for item in lots}
        self.assertIn("lot-local", noms)
        self.assertNotIn("lot-externe", noms)

        r_period = self.client.get("/api/reports/profit-by-period/", **self._auth(self.comptable))
        self.assertEqual(r_period.status_code, status.HTTP_200_OK)
        lieux = {item["lieu"] for item in r_period.json()}
        self.assertIn(self.boutique.nom, lieux)
        self.assertNotIn(self.boutique_b.nom, lieux)
