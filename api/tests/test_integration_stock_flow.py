"""
Test d'intégration : achat fournisseur -> conversion -> transfert -> vente mixte -> paiement créance.
Vérifie stocks, créances, caisse et dashboards.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from finance.models import ClientFinance
from inventaire.models import Stock
from produits.models import Produit


class IntegrationStockFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        cls.ent = entreprise
        cls.mpsl = Lieu.objects.create(
            entreprise=entreprise, nom="MPSL", code="MPSL", type_lieu=Lieu.TYPE_MPSL
        )
        cls.boutique = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique A", code="BTA", type_lieu=Lieu.TYPE_MAGASIN
        )

        cls.user_mpsl = CustomUser.objects.create_user(
            username="mpsl_user",
            password="pass",
            role=CustomUser.ROLE_MPSL,
            entreprise=entreprise,
            lieu=cls.mpsl,
        )
        cls.user_boutique = CustomUser.objects.create_user(
            username="boutique_user",
            password="pass",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.boutique,
        )
        cls.user_admin = CustomUser.objects.create_user(
            username="admin_user",
            password="pass",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
        )

        cls.client_obj = ClientFinance.objects.create(
            entreprise=entreprise,
            nom="Client Test",
            contact="0000",
        )

    def _auth_headers(self, user):
        refresh = RefreshToken.for_user(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {str(refresh.access_token)}"}

    def test_full_flow(self):
        # 1) Achat fournisseur (MPSL) : 6 sacs de 50kg
        url_achat = reverse("mpsl-achats-list")
        payload_achat = {
            "produit_nom": "Maïs sac",
            "quantite": "6",
            "unite": "sacs",
            "prix_unitaire": "100",
            "poids_par_sac": "50",
        }
        r = self.client.post(url_achat, payload_achat, format="json", **self._auth_headers(self.user_mpsl))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        # Produit créé par l'achat MPSL
        produit_id = Produit.objects.get(nom="Maïs sac", entreprise=self.ent).pk

        # 2) Conversion 1 sac -> 50 kg (MPSL)
        url_convert = reverse("mpsl-stock-convertir", args=[produit_id])
        r = self.client.post(url_convert, {"nombre_sacs": 1}, format="json", **self._auth_headers(self.user_mpsl))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # 3) Transfert vers boutique : 5 sacs + 50 kg
        url_transfert = reverse("mpsl-transferts-list")
        payload_transfert = {
            "to_lieu": self.boutique.pk,
            "lignes": [
                {"produit_id": produit_id, "quantite": "5", "unite": "sacs"},
                {"produit_id": produit_id, "quantite": "50", "unite": "kg"},
            ],
        }
        r = self.client.post(url_transfert, payload_transfert, format="json", **self._auth_headers(self.user_mpsl))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        stock_boutique = Stock.objects.get(lieu=self.boutique, produit_id=produit_id)
        self.assertEqual(stock_boutique.quantite, Decimal("5"))
        self.assertEqual(stock_boutique.quantite_kg, Decimal("50"))

        # 4) Vente mixte en kg : 270 kg (doit convertir 5 sacs + 50 kg)
        url_vente = reverse("boutique-ventes-list")
        payload_vente = {
            "lignes": [
                {"produit": produit_id, "quantite": "270", "prix_unitaire": "200", "unite": "kg"}
            ],
            "type_vente": "credit",
            "client_id": self.client_obj.pk,
            "montant_cash": "0",
        }
        r = self.client.post(url_vente, payload_vente, format="json", **self._auth_headers(self.user_boutique))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        stock_boutique.refresh_from_db()
        self.assertEqual(stock_boutique.quantite, Decimal("0"))
        self.assertEqual(stock_boutique.quantite_kg, Decimal("30"))

        # 5) Paiement partiel de la créance
        # Récupérer la créance boutique
        url_creances = reverse("boutique-creances-list")
        r = self.client.get(url_creances, **self._auth_headers(self.user_boutique))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        creance_id = r.json()["results"][0]["id"]

        url_paiement = reverse("boutique-creances-paiement", args=[creance_id])
        payload_paiement = {"montant": "10000", "date": "2026-03-21"}
        r = self.client.post(url_paiement, payload_paiement, format="json", **self._auth_headers(self.user_boutique))
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        # 6) Dashboards : vérifier caisse et créances
        url_dash_boutique = reverse("boutique-dashboard")
        r = self.client.get(url_dash_boutique, **self._auth_headers(self.user_boutique))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertEqual(Decimal(data["total_cash"]), Decimal("0"))
        self.assertEqual(Decimal(data["total_paiements_creances"]), Decimal("10000"))
        self.assertTrue(Decimal(data["total_creances"]) > Decimal("0"))

        url_dash_global = reverse("finance-dashboard")
        r = self.client.get(url_dash_global, **self._auth_headers(self.user_admin))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
