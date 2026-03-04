from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Categorie, Produit
from usine.models import LotProduction


class FactoryEndpointsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        entreprise_b = Entreprise.objects.create(nom="KONIS-B")
        cls.usine = Lieu.objects.create(entreprise=entreprise, nom="Usine", type_lieu=Lieu.TYPE_USINE)
        cls.shop = Lieu.objects.create(entreprise=entreprise, nom="Boutique A", type_lieu=Lieu.TYPE_MAGASIN)
        cls.usine_b = Lieu.objects.create(entreprise=entreprise_b, nom="Usine B", type_lieu=Lieu.TYPE_USINE)
        cls.shop_b = Lieu.objects.create(entreprise=entreprise_b, nom="Boutique B", type_lieu=Lieu.TYPE_MAGASIN)
        cls.admin = CustomUser.objects.create_user(username="admin", password="admin123", role=CustomUser.ROLE_ADMIN, entreprise=entreprise)
        cls.usine_user = CustomUser.objects.create_user(
            username="factory",
            password="factory123",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=cls.usine,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable",
            password="comptable123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        cat = Categorie.objects.create(nom="Cat")
        cls.raw = Produit.objects.create(
            categorie=cat,
            nom="Mais brut",
            code="RAW01",
            category=Produit.CATEGORY_RAW_MATERIAL,
            unite="kg",
            entreprise=entreprise,
        )
        cls.finished = Produit.objects.create(
            categorie=cat,
            nom="Anitche",
            code="FIN01",
            category=Produit.CATEGORY_FINISHED,
            unite="kg",
            entreprise=entreprise,
        )
        Stock.objects.create(produit=cls.raw, lieu=cls.usine, quantite=Decimal("200"))
        Stock.objects.create(produit=cls.finished, lieu=cls.shop_b, quantite=Decimal("999"))

    def _auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def test_raw_material_catalog_list_and_create(self):
        r0 = self.client.get("/api/factory/raw-materials/catalog/", **self._auth(self.usine_user))
        self.assertEqual(r0.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["id"] == self.raw.id for item in r0.json()))

        create_payload = {"name": "Tourteau soja", "code": "RAW02", "unit": "kg"}
        r1 = self.client.post("/api/factory/raw-materials/catalog/", create_payload, format="json", **self._auth(self.usine_user))
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.json())
        self.assertEqual(r1.json()["name"], "Tourteau soja")

        r2 = self.client.get("/api/factory/raw-materials/catalog/", **self._auth(self.usine_user))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["name"] == "Tourteau soja" for item in r2.json()))

    def test_finished_product_catalog_list_and_create(self):
        r0 = self.client.get("/api/factory/finished-products/catalog/", **self._auth(self.usine_user))
        self.assertEqual(r0.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["id"] == self.finished.id for item in r0.json()))

        create_payload = {"name": "Anitche Premium", "code": "FIN02", "unit": "kg"}
        r1 = self.client.post("/api/factory/finished-products/catalog/", create_payload, format="json", **self._auth(self.usine_user))
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.json())
        self.assertEqual(r1.json()["name"], "Anitche Premium")

    def test_factory_production_create_and_list(self):
        """Test la creation d'un lot de production via l'API."""
        payload = {
            "nom_lot": "anitche01",
            "lieu_usine": self.usine.id,
            "produit_fini": self.finished.id,
            "quantite_sacs": "60",
            "poids": "3000",
            "unite_poids": "kg",
        }
        r = self.client.post("/api/usine/lots/", payload, format="json", **self._auth(self.usine_user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        created = r.json()
        self.assertEqual(created["nom_lot"], "anitche01")

        # Verifier le stock
        stock = Stock.objects.get(produit=self.finished, lieu=self.usine)
        self.assertEqual(stock.quantite, Decimal("60"))

    def test_factory_shop_stock_and_dashboard(self):
        lot = LotProduction.objects.create(
            nom_lot="anitche02",
            lieu_usine=self.usine,
            produit_fini=self.finished,
            quantite_sacs=Decimal("20"),
            poids=Decimal("1000"),
            created_by=self.usine_user,
        )
        Stock.objects.update_or_create(produit=self.finished, lieu=self.usine, defaults={"quantite": Decimal("20")})

        r_transfer = self.client.post(
            "/api/usine/cessions/",
            {"lot": lot.id, "boutique": self.shop.id, "quantite_sacs": "5", "poids_total": "250", "prix_par_sac": "20"},
            format="json",
            **self._auth(self.usine_user),
        )
        self.assertEqual(r_transfer.status_code, status.HTTP_201_CREATED, r_transfer.json())

        rs = self.client.get("/api/usine/stocks-boutiques/", **self._auth(self.usine_user))
        self.assertEqual(rs.status_code, status.HTTP_200_OK)
        body = rs.json()
        items = body.get("results", body) if isinstance(body, dict) else body
        self.assertTrue(all(item["lieu"] != self.shop_b.id for item in items))

        rd = self.client.get("/api/factory/dashboard/", **self._auth(self.usine_user))
        self.assertEqual(rd.status_code, status.HTTP_200_OK)
        self.assertIn("last_productions", rd.json())

    def test_profit_reports_accessible_by_comptable(self):
        r1 = self.client.get("/api/reports/profit-by-lot/", **self._auth(self.comptable))
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        r2 = self.client.get("/api/reports/profit-by-period/", **self._auth(self.comptable))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

    def test_admin_can_access_factory_catalog(self):
        """Test que l'admin peut acceder au catalogue des matieres premieres."""
        r = self.client.get("/api/factory/raw-materials/catalog/", **self._auth(self.admin))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_factory_movements_journal_returns_entries_exits_and_totals(self):
        lot = LotProduction.objects.create(
            nom_lot="anitche-journal-01",
            lieu_usine=self.usine,
            produit_fini=self.finished,
            quantite_sacs=Decimal("20"),
            poids=Decimal("1000"),
            created_by=self.usine_user,
        )
        Stock.objects.update_or_create(produit=self.finished, lieu=self.usine, defaults={"quantite": Decimal("20")})

        # Creer un achat
        self.client.post(
            "/api/usine/achats/",
            {"lieu": self.usine.id, "produit_nom": "Mais", "quantite": "10", "unite": "sacs", "prix_unitaire": "2.5"},
            format="json",
            **self._auth(self.usine_user),
        )

        # Creer une cession
        self.client.post(
            "/api/usine/cessions/",
            {"lot": lot.id, "boutique": self.shop.id, "quantite_sacs": "5", "poids_total": "250", "prix_par_sac": "20"},
            format="json",
            **self._auth(self.usine_user),
        )

        r = self.client.get("/api/factory/movements-journal/", **self._auth(self.usine_user))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertIn("entries", body)
        self.assertIn("exits", body)
        self.assertIn("totals", body)
        self.assertIn("entries_value", body["totals"])
        self.assertIn("exits_value", body["totals"])

    def test_usine_achats_create_and_list(self):
        """Test la creation et la liste des achats usine."""
        payload = {
            "lieu": self.usine.id,
            "produit_nom": "Son de ble",
            "quantite": "50",
            "unite": "sacs",
            "prix_unitaire": "15.00",
            "notes": "Achat test",
        }
        r = self.client.post("/api/usine/achats/", payload, format="json", **self._auth(self.usine_user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

        r2 = self.client.get("/api/usine/achats/", **self._auth(self.usine_user))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        data = r2.json()
        # Peut etre une liste ou un objet pagine
        if isinstance(data, list):
            items = data
        else:
            items = data.get("results", [])
        self.assertTrue(any(item["produit_nom"] == "Son de ble" for item in items))

    def test_factory_cannot_transfer_to_shop_of_other_entreprise(self):
        lot = LotProduction.objects.create(
            nom_lot="anitche-cross-shop",
            lieu_usine=self.usine,
            produit_fini=self.finished,
            quantite_sacs=Decimal("10"),
            poids=Decimal("500"),
            created_by=self.usine_user,
        )
        Stock.objects.update_or_create(produit=self.finished, lieu=self.usine, defaults={"quantite": Decimal("10")})

        r = self.client.post(
            "/api/usine/cessions/",
            {"lot": lot.id, "boutique": self.shop_b.id, "quantite_sacs": "2", "poids_total": "100", "prix_par_sac": "20"},
            format="json",
            **self._auth(self.usine_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())
        self.assertIn("inter-entreprises", str(r.json()).lower())

    def test_factory_cannot_transfer_to_factory_of_other_entreprise(self):
        lot = LotProduction.objects.create(
            nom_lot="anitche-cross-factory",
            lieu_usine=self.usine,
            produit_fini=self.finished,
            quantite_sacs=Decimal("10"),
            poids=Decimal("500"),
            created_by=self.usine_user,
        )
        Stock.objects.update_or_create(produit=self.finished, lieu=self.usine, defaults={"quantite": Decimal("10")})

        r = self.client.post(
            "/api/usine/transferts-inter-usines/",
            {"lot": lot.id, "usine_destination": self.usine_b.id, "quantite_sacs": "2", "poids_total": "100", "prix_par_sac": "20"},
            format="json",
            **self._auth(self.usine_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())
        self.assertIn("inter-entreprises", str(r.json()).lower())
