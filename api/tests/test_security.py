"""
Tests sécurité KONIS : accès non autorisé, stock négatif, isolement boutique, token expiré/invalide.
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


class SecurityTests(APITestCase):
    """Tests de sécurité : permissions, stock, isolement boutique, JWT."""

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        usine = Lieu.objects.create(
            entreprise=entreprise, nom="Usine", type_lieu=Lieu.TYPE_USINE
        )
        lieu_b1 = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique 1", type_lieu=Lieu.TYPE_MAGASIN
        )
        lieu_b2 = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique 2", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin",
            password="admin123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
        )
        cls.boutique1 = CustomUser.objects.create_user(
            username="boutique1",
            password="b123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=lieu_b1,
        )
        cls.boutique2 = CustomUser.objects.create_user(
            username="boutique2",
            password="b123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=lieu_b2,
        )
        cat = Categorie.objects.create(nom="Cat", entreprise=entreprise)
        cls.produit = Produit.objects.create(
            categorie=cat, nom="P1", code="P001", unite="kg", entreprise=entreprise
        )
        Stock.objects.create(produit=cls.produit, lieu=lieu_b1, quantite=Decimal("10"))
        Stock.objects.create(produit=cls.produit, lieu=lieu_b2, quantite=Decimal("5"))

    def _auth_headers(self, user):
        refresh = RefreshToken.for_user(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {str(refresh.access_token)}"}

    def test_refus_acces_non_autorise(self):
        """Sans token, les endpoints protégés renvoient 401."""
        url = reverse("admin-produits-list")
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

        url = reverse("boutique-stock-list")
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_boutique_ne_voit_pas_admin(self):
        """Un utilisateur boutique qui appelle l'API admin reçoit 403."""
        url = reverse("admin-stocks-list")
        r = self.client.get(url, **self._auth_headers(self.boutique1))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_boutique_ne_voit_que_son_stock(self):
        """Boutique1 ne voit que le stock de son lieu (Boutique 1), pas celui de Boutique 2."""
        url = reverse("boutique-stock-list")
        r = self.client.get(url, **self._auth_headers(self.boutique1))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["lieu_nom"], "Boutique 1")
        self.assertEqual(Decimal(items[0]["quantite"]), Decimal("10"))

    def test_impossibilite_stock_negatif(self):
        """Créer une vente avec quantité > stock disponible renvoie 400."""
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
            url, payload, format="json", **self._auth_headers(self.boutique1),
            HTTP_IDEMPOTENCY_KEY="security-stock-negatif-001",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Stock insuffisant", r.json().get("detail", ""))

    def test_refus_acces_autre_boutique(self):
        """Les données d'une boutique ne sont pas accessibles par une autre (via API boutique)."""
        # boutique1 ne peut pas voir les ventes de boutique2 (l'API filtre par request.user.lieu)
        url = reverse("boutique-ventes-list")
        r = self.client.get(url, **self._auth_headers(self.boutique1))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Liste des ventes du lieu de boutique1 ; si on créait un ticket pour lieu_b2,
        # il ne serait pas dans cette liste
        data = r.json()
        ids = [t["id"] for t in (data.get("results", data) if isinstance(data, dict) else data)]
        # Créer un ticket pour boutique2 (via admin ou directement en base pour le test)
        ticket_b2 = Ticket.objects.create(
            lieu=Lieu.objects.get(nom="Boutique 2"), numero="KONIS-NORD-20260208-000001"
        )
        r = self.client.get(url, **self._auth_headers(self.boutique1))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data_after = r.json()
        ids_after = [t["id"] for t in (data_after.get("results", data_after) if isinstance(data_after, dict) else data_after)]
        self.assertNotIn(ticket_b2.id, ids_after, "Boutique1 ne doit pas voir le ticket de Boutique 2")

    def test_token_invalide_refuse(self):
        """Un token invalide ou expiré est rejeté (401)."""
        url = reverse("boutique-stock-list")
        r = self.client.get(url, HTTP_AUTHORIZATION="Bearer token_invalide_xyz")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_ne_peut_pas_creer_produit_manuel_boutique(self):
        """Un admin ne peut pas creer un produit manuel via API boutique (ReadOnly → 405)."""
        url = reverse("boutique-produits-list")
        payload = {"name": "Produit admin interdit", "initial_stock": "1"}
        r = self.client.post(url, payload, format="json", **self._auth_headers(self.admin))
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_admin_ne_peut_pas_creer_produit_via_admin_api(self):
        """L'API admin produits est en lecture seule (pas de POST)."""
        url = reverse("admin-produits-list")
        payload = {"nom": "Produit interdit", "categorie": 1, "unite": "kg"}
        r = self.client.post(url, payload, format="json", **self._auth_headers(self.admin))
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_admin_transferts_et_achats_usine_en_lecture_seule(self):
        """Les endpoints admin stock operationnel sont desormais lecture seule."""
        transfert_url = reverse("admin-transferts-list")
        achat_url = reverse("admin-achats-usine-list")
        r1 = self.client.post(
            transfert_url,
            {"from_lieu": 1, "to_lieu": 2, "lignes": [{"produit": self.produit.id, "quantite": 1}]},
            format="json",
            **self._auth_headers(self.admin),
        )
        r2 = self.client.post(
            achat_url,
            {"lieu": 1, "produit": self.produit.id, "quantite": 1},
            format="json",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(r1.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(r2.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_admin_peut_acceder_aux_endpoints_boutique_pour_gestion(self):
        """L'admin peut acceder aux endpoints boutique pour la gestion (avec parametre lieu)."""
        # L'admin peut lister les stocks (mais obtient une liste vide sans parametre lieu)
        r_stock = self.client.get(reverse("boutique-stock-list"), **self._auth_headers(self.admin))
        self.assertEqual(r_stock.status_code, status.HTTP_200_OK)
        # L'admin peut specifier un lieu pour voir le stock d'une boutique
        lieu_b1 = Lieu.objects.get(nom="Boutique 1")
        r_stock_lieu = self.client.get(
            reverse("boutique-stock-list") + f"?lieu={lieu_b1.id}",
            **self._auth_headers(self.admin)
        )
        self.assertEqual(r_stock_lieu.status_code, status.HTTP_200_OK)
        
        # L'admin peut lister les ventes
        r_ventes = self.client.get(reverse("boutique-ventes-list"), **self._auth_headers(self.admin))
        self.assertEqual(r_ventes.status_code, status.HTTP_200_OK)
