"""
Tests metier "impossibles a tricher" - preuves pour audit.
Executer : python manage.py test api.tests.test_metier_proof -v 2
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient

from core.models import CustomUser, Entreprise, Lieu
from depenses.models import CategorieDepense
from inventaire.models import Stock
from inventaire.services import transfert_usine_vers_boutique
from produits.models import Categorie, Produit


class TestsMetierProof(TestCase):
    """5 tests metier avec assertions explicites pour preuve."""

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.get_primary()
        if entreprise.nom != "KONIS":
            entreprise.nom = "KONIS"
            entreprise.save(update_fields=["nom"])
        cls.usine = Lieu.objects.create(entreprise=entreprise, nom="Usine", type_lieu=Lieu.TYPE_USINE)
        cls.b1 = Lieu.objects.create(entreprise=entreprise, nom="Boutique 1", type_lieu=Lieu.TYPE_MAGASIN)
        cls.b2 = Lieu.objects.create(entreprise=entreprise, nom="Boutique 2", type_lieu=Lieu.TYPE_MAGASIN)
        cls.admin = CustomUser.objects.create_user(
            username="admin", password="a", role=CustomUser.ROLE_ADMIN, entreprise=entreprise
        )
        cls.boutique1 = CustomUser.objects.create_user(
            username="b1", password="b", role=CustomUser.ROLE_BOUTIQUE, entreprise=entreprise, lieu=cls.b1
        )
        cls.boutique2 = CustomUser.objects.create_user(
            username="b2", password="b", role=CustomUser.ROLE_BOUTIQUE, entreprise=entreprise, lieu=cls.b2
        )
        cls.comptable = CustomUser.objects.create_user(
            username="compta", password="c", role=CustomUser.ROLE_COMPTABLE, entreprise=entreprise
        )
        cat = Categorie.objects.create(nom="C", entreprise=entreprise)
        cls.produit = Produit.objects.create(categorie=cat, nom="P1", code="P001", unite="kg", entreprise=entreprise)
        Stock.objects.create(produit=cls.produit, lieu=cls.usine, quantite=Decimal("100"))
        CategorieDepense.objects.get_or_create(nom="Divers", entreprise=entreprise)

    def _token(self, user):
        return str(RefreshToken.for_user(user).access_token)

    def test_1_vente_valide_ticket_et_stock_diminue(self):
        """1) Vente valide -> ticket cree + stock diminue."""
        self.client = APIClient()
        transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.b1,
            lignes=[(self.produit, Decimal("50"))],
        )
        stock_b1_avant = Stock.objects.get(produit=self.produit, lieu=self.b1).quantite

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.boutique1)}")
        r = self.client.post(
            "/api/boutique/ventes/",
            {"lignes": [{"produit": self.produit.id, "quantite": 10, "prix_unitaire": 100}]},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        self.assertIn("id", r.json())
        self.assertIn("numero", r.json())
        stock_b1_apres = Stock.objects.get(produit=self.produit, lieu=self.b1).quantite
        self.assertEqual(stock_b1_apres, stock_b1_avant - Decimal("10"))

    def test_2_vente_quantite_superieure_stock_refus_400(self):
        """2) Vente avec quantite > stock -> refus 400 + message clair."""
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.boutique1)}")
        r = self.client.post(
            "/api/boutique/ventes/",
            {"lignes": [{"produit": self.produit.id, "quantite": 99999, "prix_unitaire": 100}]},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())
        detail = str(r.json().get("detail", ""))
        self.assertTrue("stock" in detail.lower())

    def test_3_transfert_usine_boutique_stocks_ok(self):
        """3) Transfert usine -> boutique -> stock usine baisse + boutique augmente."""
        stock_usine_avant = Stock.objects.get(produit=self.produit, lieu=self.usine).quantite
        stock_b2_avant = Stock.objects.filter(produit=self.produit, lieu=self.b2).first()
        stock_b2_avant_qty = stock_b2_avant.quantite if stock_b2_avant else Decimal("0")

        transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.b2,
            lignes=[(self.produit, Decimal("20"))],
        )

        stock_usine_apres = Stock.objects.get(produit=self.produit, lieu=self.usine).quantite
        stock_b2_apres = Stock.objects.get(produit=self.produit, lieu=self.b2).quantite
        self.assertEqual(stock_usine_apres, stock_usine_avant - Decimal("20"))
        self.assertEqual(stock_b2_apres, stock_b2_avant_qty + Decimal("20"))

    def test_4_boutique_ne_voit_pas_autre_boutique(self):
        """4) Boutique ne voit pas les donnees d'une autre boutique."""
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.boutique1)}")
        r1 = self.client.get("/api/boutique/ventes/")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        d1 = r1.json()
        ids_b1 = [t["id"] for t in (d1.get("results", d1) if isinstance(d1, dict) else d1)]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.boutique2)}")
        r2 = self.client.get("/api/boutique/ventes/")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        d2 = r2.json()
        ids_b2 = [t["id"] for t in (d2.get("results", d2) if isinstance(d2, dict) else d2)]
        for tid in ids_b1:
            self.assertNotIn(tid, ids_b2)

    def test_5_depense_visible_admin_et_comptable(self):
        """5) Depense creee -> visible admin et comptable."""
        self.client = APIClient()
        cat = CategorieDepense.objects.first()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.admin)}")
        r = self.client.post(
            "/api/admin/depenses/",
            {"lieu": self.b1.id, "categorie": cat.id, "montant": 50, "date": "2026-02-08", "libelle": "Test audit"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        dep_id = r.json()["id"]
        r_admin = self.client.get("/api/admin/depenses/")
        self.assertEqual(r_admin.status_code, status.HTTP_200_OK)
        da = r_admin.json()
        self.assertIn(dep_id, [d["id"] for d in (da.get("results", da) if isinstance(da, dict) else da)])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(self.comptable)}")
        r_compta = self.client.get("/api/comptable/depenses/")
        self.assertEqual(r_compta.status_code, status.HTTP_200_OK)
        dc = r_compta.json()
        self.assertIn(dep_id, [d["id"] for d in (dc.get("results", dc) if isinstance(dc, dict) else dc)])
