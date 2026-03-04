from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from ventes.models import Facture, LigneFacture


class FacturePdfTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS Industrie")
        entreprise_b = Entreprise.objects.create(nom="KONIS Externe")
        cls.lieu_a = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique A",
            code="BA",
            type_lieu=Lieu.TYPE_MAGASIN,
            adresse="Centre Ville",
        )
        cls.lieu_b = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique B",
            code="BB",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.lieu_ext = Lieu.objects.create(
            entreprise=entreprise_b,
            nom="Boutique X",
            code="BX",
            type_lieu=Lieu.TYPE_MAGASIN,
        )

        cls.user_a = CustomUser.objects.create_user(
            username="user_a",
            password="pass123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu_a,
        )
        cls.user_b = CustomUser.objects.create_user(
            username="user_b",
            password="pass123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=cls.lieu_b,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_pdf",
            password="pass123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="comptable_pdf",
            password="pass123",
            role=CustomUser.ROLE_COMPTABLE,
            entreprise=entreprise,
        )

        cls.facture = Facture.objects.create(
            lieu=cls.lieu_a,
            numero="INV-BA-20260228-000001",
            source_role=Facture.SOURCE_BOUTIQUE,
            created_by=cls.user_a,
            client_nom="Client PDF",
            client_contact="90000000",
            notes="Facture test",
            total=Decimal("2150.00"),
        )
        LigneFacture.objects.create(
            facture=cls.facture,
            description="Produit aliment 50kg",
            quantite=Decimal("2"),
            prix_unitaire=Decimal("1000"),
        )
        LigneFacture.objects.create(
            facture=cls.facture,
            description="Service mouture",
            quantite=Decimal("1"),
            prix_unitaire=Decimal("150"),
        )
        cls.facture_ext = Facture.objects.create(
            lieu=cls.lieu_ext,
            numero="INV-BX-20260228-000001",
            source_role=Facture.SOURCE_BOUTIQUE,
            total=Decimal("99.00"),
        )
        LigneFacture.objects.create(
            facture=cls.facture_ext,
            description="Externe",
            quantite=Decimal("1"),
            prix_unitaire=Decimal("99"),
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_pdf_requires_authentication(self):
        url = reverse("facture-pdf", kwargs={"facture_id": self.facture.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pdf_permissions_lieu_scope(self):
        url = reverse("facture-pdf", kwargs={"facture_id": self.facture.id})
        forbidden = self.client.get(url, **self._auth(self.user_b))
        self.assertEqual(forbidden.status_code, status.HTTP_404_NOT_FOUND)
        allowed = self.client.get(url, **self._auth(self.admin))
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_pdf_is_generated_and_contains_expected_values(self):
        url = reverse("facture-pdf", kwargs={"facture_id": self.facture.id})
        response = self.client.get(url, **self._auth(self.user_a))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.get("Content-Type"), "application/pdf")
        self.assertIn("inline;", response.get("Content-Disposition", ""))
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(b"TOTAL GENERAL", response.content)
        self.assertIn(b"2 150.00 FCFA", response.content)
        self.assertIn(b"Service mouture", response.content)

    def test_pdf_download_mode(self):
        url = reverse("facture-pdf", kwargs={"facture_id": self.facture.id}) + "?download=1"
        response = self.client.get(url, **self._auth(self.user_a))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("attachment;", response.get("Content-Disposition", ""))

    def test_pdf_reprint_is_identical(self):
        url = reverse("facture-pdf", kwargs={"facture_id": self.facture.id})
        first = self.client.get(url, **self._auth(self.user_a))
        second = self.client.get(url, **self._auth(self.user_a))
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.content, second.content)

    def test_print_alias_returns_same_pdf(self):
        pdf_url = reverse("facture-pdf", kwargs={"facture_id": self.facture.id})
        print_url = reverse("facture-print", kwargs={"facture_id": self.facture.id})
        pdf_resp = self.client.get(pdf_url, **self._auth(self.user_a))
        print_resp = self.client.get(print_url, **self._auth(self.user_a))
        self.assertEqual(pdf_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(print_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf_resp.get("Content-Type"), "application/pdf")
        self.assertEqual(print_resp.get("Content-Type"), "application/pdf")
        self.assertEqual(pdf_resp.content, print_resp.content)

    def test_comptable_cannot_access_other_entreprise_facture_pdf(self):
        url = reverse("facture-pdf", kwargs={"facture_id": self.facture_ext.id})
        response = self.client.get(url, **self._auth(self.comptable))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
