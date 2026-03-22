"""
Tests ventes KONIS : stock diminue, stock insuffisant -> 400, numéros ticket uniques.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APITestCase

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
from produits.models import Categorie, Produit
from ventes.models import Ticket
from ventes.services import vente_boutique


class VenteBoutiqueTests(APITestCase):
    """Tests du service de vente : stock, numéros ticket."""

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        cls.lieu = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique Test", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.user = CustomUser.objects.create_user(
            username="boutique_test",
            password="b123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu,
        )
        cat = Categorie.objects.create(nom="Cat", entreprise=entreprise)
        cls.produit = Produit.objects.create(
            categorie=cat, nom="Produit Test", code="P001", unite="kg",
            entreprise=entreprise,
        )
        Stock.objects.create(
            produit=cls.produit, lieu=cls.lieu, quantite=Decimal("50")
        )

    def _auth_headers(self, idempotency_key=None):
        refresh = RefreshToken.for_user(self.user)
        headers = {"HTTP_AUTHORIZATION": f"Bearer {str(refresh.access_token)}"}
        if idempotency_key:
            headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
        return headers

    def test_vente_ok_stock_diminue(self):
        """Créer une vente valide diminue le stock en base."""
        url = reverse("boutique-ventes-list")
        payload = {
            "lignes": [
                {
                    "produit": self.produit.pk,
                    "quantite": 10,
                    "prix_unitaire": 150.50,
                }
            ]
        }
        r = self.client.post(
            url, payload, format="json", **self._auth_headers(idempotency_key="test-vente-ok-1")
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        stock = Stock.objects.get(produit=self.produit, lieu=self.lieu)
        self.assertEqual(stock.quantite, Decimal("40"), "Stock doit passer de 50 à 40")

    def test_stock_insuffisant_400(self):
        """Quantité > stock disponible renvoie 400."""
        url = reverse("boutique-ventes-list")
        payload = {
            "lignes": [
                {
                    "produit": self.produit.pk,
                    "quantite": 999,
                    "prix_unitaire": 100,
                }
            ]
        }
        r = self.client.post(
            url, payload, format="json", **self._auth_headers(idempotency_key="test-stock-insuf-1")
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Stock insuffisant", r.json().get("detail", ""))

    def test_ticket_numero_auto_non_null(self):
        """Le numéro de ticket est généré automatiquement et n'est jamais null."""
        t, _ = vente_boutique(self.lieu, [(self.produit, Decimal("1"), Decimal("100"))])
        self.assertIsNotNone(t.numero)
        self.assertTrue(len(t.numero) > 0)
        t.refresh_from_db()
        self.assertIsNotNone(t.numero)

    def test_ticket_numero_unique_sur_2_ventes(self):
        """2 ventes consécutives produisent 2 numéros de ticket différents."""
        t1, _ = vente_boutique(
            self.lieu,
            [(self.produit, Decimal("1"), Decimal("100"))],
        )
        t2, _ = vente_boutique(
            self.lieu,
            [(self.produit, Decimal("1"), Decimal("100"))],
        )
        self.assertNotEqual(t1.numero, t2.numero)
        self.assertIsNotNone(t1.numero)
        self.assertIsNotNone(t2.numero)

    def test_ticket_numero_format(self):
        """Format KONIS-{CODE}-{YYYYMMDD}-{SEQ:06d}."""
        self.lieu.code = "CENTRE"
        self.lieu.save()
        t, _ = vente_boutique(self.lieu, [(self.produit, Decimal("1"), Decimal("100"))])
        parts = t.numero.split("-")
        self.assertEqual(parts[0], "KONIS")
        self.assertEqual(parts[1], "CENTRE")
        self.assertEqual(len(parts[2]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[3]), 6)  # SEQ
        self.assertTrue(parts[3].isdigit())
