"""
Tests authentification KONIS : login (POST /api/auth/login/).
Diagnostic des problèmes de connexion.
"""
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import CustomUser, Entreprise, Lieu


class AuthLoginTests(APITestCase):
    """Tests du endpoint de login."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        lieu_usine = Lieu.objects.create(
            entreprise=entreprise,
            nom="Usine Centrale",
            type_lieu=Lieu.TYPE_USINE,
        )
        lieu_boutique = Lieu.objects.create(
            entreprise=entreprise,
            nom="Boutique Centre",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin",
            password="admin123",
            role=CustomUser.ROLE_ADMIN,
            entreprise=entreprise,
        )
        cls.boutique = CustomUser.objects.create_user(
            username="boutique1",
            password="boutique123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            lieu=lieu_boutique,
        )
        cls.usine = CustomUser.objects.create_user(
            username="usine1",
            password="usine123",
            email="usine1@konis.local",
            role=CustomUser.ROLE_USINE,
            entreprise=entreprise,
            lieu=lieu_usine,
        )
        cls.inactive_user = CustomUser.objects.create_user(
            username="inactive",
            password="inactive123",
            role=CustomUser.ROLE_BOUTIQUE,
            entreprise=entreprise,
            is_active=False,
        )

    def test_login_ok_returns_tokens_and_user(self):
        """Connexion réussie retourne 200 avec access, refresh et user."""
        url = reverse("auth:auth-login")
        payload = {"username": "admin", "password": "admin123"}
        # X-Proxy: secret partagé pour récupérer tokens dans le body (comportement Next.js SSR)
        headers = {"HTTP_X_PROXY": settings.INTERNAL_API_SECRET}
        r = self.client.post(
            url, payload, format="json", **headers
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIn("user", data)
        user = data["user"]
        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["role"], "admin")
        self.assertIn("role_display", user)

    def test_login_invalid_password_401(self):
        """Mot de passe incorrect renvoie 401."""
        url = reverse("auth:auth-login")
        payload = {"username": "admin", "password": "wrong"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)
        data = r.json()
        self.assertIn("detail", data)

    def test_login_unknown_user_401(self):
        """Utilisateur inexistant renvoie 401."""
        url = reverse("auth:auth-login")
        payload = {"username": "inexistant", "password": "any"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_inactive_user_401(self):
        """Utilisateur avec is_active=False renvoie 401."""
        url = reverse("auth:auth-login")
        payload = {"username": "inactive", "password": "inactive123"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_boutique_with_lieu_returns_lieu(self):
        """Compte boutique avec magasin assigné retourne user.lieu."""
        url = reverse("auth:auth-login")
        payload = {"username": "boutique1", "password": "boutique123"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        user = r.json().get("user", {})
        self.assertIsNotNone(user.get("lieu"))
        lieu = user["lieu"]
        self.assertIn("id", lieu)
        self.assertIn("nom", lieu)
        self.assertEqual(lieu["nom"], "Boutique Centre")
        self.assertIn("type_lieu", lieu)
        self.assertEqual(lieu["type_lieu"], "magasin")

    def test_login_requires_username_password(self):
        """Champs username et password obligatoires (400 si manquants)."""
        url = reverse("auth:auth-login")
        # Sans password
        r = self.client.post(
            url, {"username": "admin"}, format="json"
        )
        self.assertIn(r.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))

    def test_login_factory_with_email_sets_is_factory(self):
        """Un utilisateur usine peut se connecter avec email et reçoit is_factory."""
        url = reverse("auth:auth-login")
        payload = {"username": "usine1@konis.local", "password": "usine123"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertIn("user", data)
        self.assertTrue(data["user"]["is_factory"])
        self.assertEqual(data["user"]["role_normalized"], "factory")
        # Sans username
        r = self.client.post(
            url, {"password": "admin123"}, format="json"
        )
        self.assertIn(r.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))

    def _login_tokens(self, username="admin", password="admin123"):
        """Login proxy Next pour récupérer access/refresh dans le body."""
        url = reverse("auth:auth-login")
        r = self.client.post(
            url,
            {"username": username, "password": password},
            format="json",
            HTTP_X_PROXY=settings.INTERNAL_API_SECRET,
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        return data["access"], data["refresh"]

    def test_refresh_returns_access_and_refresh(self):
        """Refresh renvoie access et refresh dans le body (contrat API frontend)."""
        _, refresh = self._login_tokens()
        url = reverse("auth:auth-refresh")
        r = self.client.post(url, {"refresh": refresh}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertTrue(isinstance(data["access"], str) and len(data["access"]) > 20)
        self.assertTrue(isinstance(data["refresh"], str) and len(data["refresh"]) > 20)

    def test_logout_blacklists_refresh_token(self):
        """Après logout, le refresh token ne peut plus être utilisé."""
        access, refresh = self._login_tokens()

        logout_url = reverse("auth:auth-logout")
        r = self.client.post(
            logout_url,
            {"refresh": refresh},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

        refresh_url = reverse("auth:auth-refresh")
        r2 = self.client.post(refresh_url, {"refresh": refresh}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_401_UNAUTHORIZED)
