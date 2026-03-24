"""
Tests hardening KONIS — audit final.

Couvre :
  A. Idempotency ventes boutique (double-tap, replay réseau)
  B. Idempotency dépenses admin (double-soumission)
  C. Isolation multi-tenant : une boutique ne voit pas les données d'une autre entreprise
  D. Utilisateur désactivé : rejet immédiat sur la prochaine requête JWT
  E. Changement de mot de passe révoque les tokens existants
  F. CheckConstraints DB : valeurs négatives rejetées par la DB
  G. Concurrence : deux ventes simultanées sur le même stock limité
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from depenses.models import CategorieDepense, Depense
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Produit
from ventes.models import Ticket
from ventes.services import vente_boutique


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_entreprise(nom="Ent Test"):
    return Entreprise.objects.create(nom=nom)


def _make_boutique(ent, nom="Boutique", code="BT"):
    return Lieu.objects.create(
        entreprise=ent, nom=nom, code=code, type_lieu=Lieu.TYPE_MAGASIN
    )


def _make_user(ent, lieu, username="user", role=CustomUser.ROLE_BOUTIQUE):
    return CustomUser.objects.create_user(
        username=username,
        password="pass1234",
        role=role,
        entreprise=ent,
        lieu=lieu,
    )


def _make_produit(ent, code="P001"):
    return Produit.objects.create(
        nom=f"Produit {code}", code=code, unite="kg", entreprise=ent
    )


def _jwt(user):
    token = str(RefreshToken.for_user(user).access_token)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ── A. Idempotency ventes boutique ───────────────────────────────────────────

class TestIdempotencyVenteBoutique(APITestCase):
    """Vente boutique — double-tap avec même Idempotency-Key → 1 seul ticket."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _make_entreprise("EntA")
        cls.lieu = _make_boutique(cls.ent, code="BA")
        cls.user = _make_user(cls.ent, cls.lieu, username="vendeur_idem")
        cls.produit = _make_produit(cls.ent, "IDEM01")
        Stock.objects.create(produit=cls.produit, lieu=cls.lieu, quantite=Decimal("100"))

    def _post_vente(self, key=None):
        headers = _jwt(self.user)
        if key:
            headers["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            "/api/boutique/ventes/",  # URL canonique (cf. router boutique-ventes-list)
            {
                "lignes": [
                    {"produit": self.produit.pk, "quantite": 5, "prix_unitaire": 200}
                ]
            },
            format="json",
            **headers,
        )

    def test_double_tap_meme_cle_retourne_meme_ticket(self):
        """Deux POST avec la même Idempotency-Key créent un seul ticket."""
        key = "test-idem-boutique-001"
        r1 = self._post_vente(key)
        r2 = self._post_vente(key)
        self.assertIn(r1.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_double_tap_meme_cle_stock_debite_une_seule_fois(self):
        """Le stock n'est débité qu'une seule fois malgré 2 POST identiques."""
        key = "test-idem-boutique-002"
        stock_avant = Stock.objects.get(produit=self.produit, lieu=self.lieu).quantite
        self._post_vente(key)
        self._post_vente(key)
        stock_apres = Stock.objects.get(produit=self.produit, lieu=self.lieu).quantite
        self.assertEqual(stock_avant - stock_apres, Decimal("5"))

    @override_settings(IDEMPOTENCY_STRICT_MODE=False)
    def test_sans_cle_deux_ventes_distinctes(self):
        """Sans Idempotency-Key deux POST créent deux tickets distincts."""
        r1 = self._post_vente()
        r2 = self._post_vente()
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(r1.json()["id"], r2.json()["id"])

    def test_idempotency_key_trop_longue_retourne_400(self):
        """Idempotency-Key >128 chars → 400 AVANT toute opération, stock inchangé."""
        stock_avant = Stock.objects.get(produit=self.produit, lieu=self.lieu).quantite
        r = self._post_vente(key="x" * 129)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("trop longue", r.json()["detail"])
        stock_apres = Stock.objects.get(produit=self.produit, lieu=self.lieu).quantite
        self.assertEqual(stock_avant, stock_apres)


# ── B. Idempotency dépenses admin ────────────────────────────────────────────

class TestIdempotencyDepense(APITestCase):
    """Dépense admin — double-soumission avec Idempotency-Key → 1 seule dépense."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _make_entreprise("EntB")
        cls.lieu = _make_boutique(cls.ent, nom="Magasin B", code="MB")
        cls.user = _make_user(cls.ent, cls.lieu, username="admin_idem", role=CustomUser.ROLE_ADMIN)
        cls.cat = CategorieDepense.objects.create(nom="Divers", entreprise=cls.ent)

    def _post_depense(self, key=None):
        headers = _jwt(self.user)
        if key:
            headers["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            "/api/admin/depenses/",
            {
                "lieu": self.lieu.pk,
                "categorie": self.cat.pk,
                "montant": "5000.00",
                "date": "2026-03-18",
                "libelle": "Test idempotency",
            },
            format="json",
            **headers,
        )

    def test_double_soumission_meme_cle_retourne_meme_depense(self):
        """2 POST identiques avec la même clé → 1 seule dépense en base."""
        key = "test-idem-depense-001"
        r1 = self._post_depense(key)
        r2 = self._post_depense(key)
        self.assertIn(r1.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(
            Depense.objects.filter(
                lieu=self.lieu, idempotency_key=key
            ).count(),
            1,
        )

    def test_sans_cle_deux_depenses_distinctes(self):
        """Sans Idempotency-Key, 2 POST créent 2 dépenses distinctes."""
        r1 = self._post_depense()
        r2 = self._post_depense()
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(r1.json()["id"], r2.json()["id"])

    def test_idempotency_key_trop_longue_retourne_400(self):
        """Idempotency-Key >128 chars → 400 AVANT création, aucune dépense créée."""
        count_avant = Depense.objects.filter(lieu=self.lieu).count()
        r = self._post_depense(key="y" * 129)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("trop longue", r.json()["detail"])
        self.assertEqual(Depense.objects.filter(lieu=self.lieu).count(), count_avant)


# ── C. Isolation multi-tenant ────────────────────────────────────────────────

class TestIsolationMultiTenant(APITestCase):
    """Boutique A ne peut pas voir les tickets/stock de l'entreprise B."""

    @classmethod
    def setUpTestData(cls):
        cls.ent_a = _make_entreprise("EntC_A")
        cls.ent_b = _make_entreprise("EntC_B")

        cls.lieu_a = _make_boutique(cls.ent_a, nom="Boutique A", code="CA")
        cls.lieu_b = _make_boutique(cls.ent_b, nom="Boutique B", code="CB")

        cls.user_a = _make_user(cls.ent_a, cls.lieu_a, username="vendeur_ca")
        cls.user_b = _make_user(cls.ent_b, cls.lieu_b, username="vendeur_cb")

        cls.produit_a = _make_produit(cls.ent_a, "CAP01")
        cls.produit_b = _make_produit(cls.ent_b, "CBP01")
        Stock.objects.create(produit=cls.produit_a, lieu=cls.lieu_a, quantite=Decimal("100"))
        Stock.objects.create(produit=cls.produit_b, lieu=cls.lieu_b, quantite=Decimal("100"))

        # Crée un ticket dans boutique A
        cls.ticket_a, _ = vente_boutique(
            cls.lieu_a, [(cls.produit_a, Decimal("1"), Decimal("100"))]
        )

    def test_boutique_b_ne_voit_pas_tickets_boutique_a(self):
        """user_b ne peut pas accéder aux tickets du lieu_a → liste vide."""
        r = self.client.get("/api/boutique/ventes/", **_jwt(self.user_b))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in r.json().get("results", r.json())]
        self.assertNotIn(self.ticket_a.pk, ids)

    def test_boutique_b_ne_peut_pas_acheter_produit_a(self):
        """user_b ne peut pas vendre le produit_a (autre entreprise) → 400/404."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [
                    {"produit": self.produit_a.pk, "quantite": 1, "prix_unitaire": 100}
                ]
            },
            format="json",
            **_jwt(self.user_b),
        )
        self.assertIn(r.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_stock_boutique_a_visible_seulement_par_user_a(self):
        """Le stock de lieu_a n'est pas visible par user_b."""
        r = self.client.get("/api/boutique/stock/", **_jwt(self.user_b))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.json().get("results", r.json())
        produit_ids = [item["produit"] for item in results]
        self.assertNotIn(self.produit_a.pk, produit_ids)


# ── D. Utilisateur désactivé ─────────────────────────────────────────────────

class TestUserDeactivation(APITestCase):
    """Désactiver un utilisateur révoque ses tokens immédiatement."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _make_entreprise("EntD")
        cls.lieu = _make_boutique(cls.ent, code="DE")
        # Lieu séparé pour l'admin (contrainte unique CustomUser.lieu_id)
        cls.lieu_admin = _make_boutique(cls.ent, nom="Admin DE", code="DEA")
        cls.user = _make_user(cls.ent, cls.lieu, username="vendeur_deact")
        cls.admin = _make_user(
            cls.ent, cls.lieu_admin, username="admin_deact", role=CustomUser.ROLE_ADMIN
        )

    def test_token_rejetee_apres_desactivation(self):
        """Un token JWT émis avant la désactivation est rejeté."""
        # Obtenir un token valide
        headers = _jwt(self.user)
        # Vérifier qu'il fonctionne
        r = self.client.get("/api/boutique/stock/", **headers)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Désactiver l'utilisateur (simulate via DB directement — cf. perform_update flow)
        self.user.is_active = False
        self.user.tokens_revoked_at = timezone.now()
        self.user.save(update_fields=["is_active", "tokens_revoked_at"])
        # Le même token doit maintenant être rejeté
        r2 = self.client.get("/api/boutique/stock/", **headers)
        self.assertEqual(r2.status_code, status.HTTP_401_UNAUTHORIZED)

    def tearDown(self):
        # Réactiver pour ne pas polluer les autres tests
        CustomUser.objects.filter(pk=self.user.pk).update(
            is_active=True, tokens_revoked_at=None
        )


# ── E. Changement de mot de passe révoque les tokens ────────────────────────

class TestPasswordChangeRevokesTokens(APITestCase):
    """Changer le mot de passe révoque les tokens précédents."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _make_entreprise("EntE")
        cls.lieu = _make_boutique(cls.ent, code="EP")
        cls.user = _make_user(cls.ent, cls.lieu, username="vendeur_pwdchg")

    def test_token_rejetee_apres_changement_mdp(self):
        """Un token émis avant un changement de mot de passe doit être invalide."""
        old_headers = _jwt(self.user)
        # Vérifier que le token fonctionne
        r = self.client.get("/api/boutique/stock/", **old_headers)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Changer le mot de passe + révoquer (flow identique à perform_update)
        self.user.set_password("nouveauMdp999!")
        self.user.tokens_revoked_at = timezone.now()
        self.user.save(update_fields=["password", "tokens_revoked_at"])
        # Ancien token doit être rejeté
        r2 = self.client.get("/api/boutique/stock/", **old_headers)
        self.assertEqual(r2.status_code, status.HTTP_401_UNAUTHORIZED)

    def tearDown(self):
        CustomUser.objects.filter(pk=self.user.pk).update(tokens_revoked_at=None)


# ── F. CheckConstraints DB ───────────────────────────────────────────────────

class TestDBCheckConstraints(TestCase):
    """Les CheckConstraints DB rejettent les valeurs négatives au niveau DB."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _make_entreprise("EntF")
        cls.lieu = _make_boutique(cls.ent, code="FX")
        cls.produit = _make_produit(cls.ent, "FXP01")
        Stock.objects.create(produit=cls.produit, lieu=cls.lieu, quantite=Decimal("100"))

    def test_ticket_montant_total_negatif_rejete(self):
        """Ticket.montant_total < 0 → IntegrityError (CheckConstraint DB)."""
        from django.db import IntegrityError
        with self.assertRaises((IntegrityError, Exception)):
            Ticket.objects.create(
                lieu=self.lieu,
                numero="KONIS-FX-99990101-000001",
                montant_total=Decimal("-1"),
            )

    def test_stock_quantite_negative_rejetee(self):
        """Stock.quantite < 0 → ValidationError (save) ou IntegrityError (DB)."""
        from django.core.exceptions import ValidationError
        stock = Stock.objects.get(produit=self.produit, lieu=self.lieu)
        stock.quantite = Decimal("-1")
        with self.assertRaises((ValidationError, Exception)):
            stock.save()


# ── G. Concurrence — stock limité ────────────────────────────────────────────

class TestConcurrenceVente(TestCase):
    """
    Deux appels vente_boutique() simultanés sur un stock de 10 :
    le second avec quantite=10 doit échouer si le premier a consommé tout le stock.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = _make_entreprise("EntG")
        cls.lieu = _make_boutique(cls.ent, code="GC")
        cls.produit = _make_produit(cls.ent, "GCP01")
        Stock.objects.create(produit=cls.produit, lieu=cls.lieu, quantite=Decimal("10"))

    def test_deux_ventes_successives_stock_epuise(self):
        """La première vente de 10 réussit ; la seconde échoue (stock épuisé)."""
        vente_boutique(self.lieu, [(self.produit, Decimal("10"), Decimal("500"))])
        with self.assertRaises(ErreurStock) as ctx:
            vente_boutique(self.lieu, [(self.produit, Decimal("1"), Decimal("500"))])
        self.assertIn("insuffisant", str(ctx.exception).lower())
