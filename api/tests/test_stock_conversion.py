"""
Tests conversion sacs -> kg (boutique) + idempotence.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APITestCase

from core.models import CustomUser, Entreprise, Lieu
from inventaire.models import Stock
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
