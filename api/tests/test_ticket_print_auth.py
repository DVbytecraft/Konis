"""
Tests d'accès endpoint impression ticket.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from produits.models import Categorie, Produit
from ventes.models import LigneVente, Ticket


class TicketPrintAuthTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        entreprise_b = Entreprise.objects.create(nom="KONIS-B")
        cls.lieu = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique Centre",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.lieu_b = Lieu.objects.create(
            entreprise=entreprise_b,
            nom="Boutique Externe",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.user = CustomUser.objects.create_user(
            username="boutique_print",
            password="print123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable_print",
            password="print123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )
        cat_a = Categorie.objects.create(nom="Cat", entreprise=entreprise)
        cat_b = Categorie.objects.create(nom="Cat", entreprise=entreprise_b)
        produit = Produit.objects.create(categorie=cat_a, nom="P1", code="P001", unite="kg", entreprise=entreprise)
        produit_b = Produit.objects.create(categorie=cat_b, nom="P2", code="P002", unite="kg", entreprise=entreprise_b)
        cls.ticket = Ticket.objects.create(lieu=cls.lieu, numero="KONIS-CENTRE-20260221-000001")
        LigneVente.objects.create(ticket=cls.ticket, produit=produit, quantite=Decimal("1"), prix_unitaire=Decimal("100"))
        cls.ticket_b = Ticket.objects.create(lieu=cls.lieu_b, numero="KONIS-EXT-20260221-000001")
        LigneVente.objects.create(ticket=cls.ticket_b, produit=produit_b, quantite=Decimal("1"), prix_unitaire=Decimal("100"))

    def test_ticket_print_requires_authentication(self):
        url = reverse("ticket-print", kwargs={"ticket_id": self.ticket.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ticket_print_authenticated_access(self):
        access = str(RefreshToken.for_user(self.user).access_token)
        url = reverse("ticket-print", kwargs={"ticket_id": self.ticket.id})
        r = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("text/html", r.get("Content-Type", ""))

    def test_comptable_cannot_print_ticket_of_other_entreprise(self):
        access = str(RefreshToken.for_user(self.comptable).access_token)
        url = reverse("ticket-print", kwargs={"ticket_id": self.ticket_b.id})
        r = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
