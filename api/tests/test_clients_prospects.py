"""
Tests clients & prospects KONIS.

Couvre :
  A. POST /boutique/clients/ — création prospect, lieu enregistré
  B. POST /boutique/clients/ — création client explicite
  C. POST /boutique/clients/ — idempotence (nom existant → 200)
  D. POST /boutique/clients/ — comptable peut créer
  E. POST /boutique/clients/ — rôle non autorisé → 403
  F. Auto-upgrade prospect → client lors d'un achat
  G. GET /admin/clients/ — admin voit tous les clients avec lieu_nom
  H. GET /admin/clients/?statut= — filtre statut
  I. GET /admin/clients/?lieu=  — filtre boutique
  J. GET /admin/clients/?search= — filtre recherche
  K. GET /admin/clients/ — comptable peut accéder
  L. GET /admin/clients/ — boutique ne peut pas accéder (403)
  M. Isolation multi-tenant — admin autre entreprise ne voit pas les données
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from finance.models import ClientFinance
from inventaire.models import Stock
from produits.models import Categorie, Produit


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tok(user):
    return str(RefreshToken.for_user(user).access_token)


def _auth(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {_tok(user)}"}


# ── Fixtures partagées ────────────────────────────────────────────────────────

class _Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="KONIS Clients Test")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique Nord", type_lieu=Lieu.TYPE_MAGASIN, code="BN"
        )
        cls.boutique2 = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique Sud", type_lieu=Lieu.TYPE_MAGASIN, code="BS"
        )

        cls.user_boutique = CustomUser.objects.create_user(
            username="bq_nord", password="x", role=CustomUser.ROLE_BOUTIQUE,
            entreprise=cls.ent, lieu=cls.boutique,
        )
        cls.user_boutique2 = CustomUser.objects.create_user(
            username="bq_sud", password="x", role=CustomUser.ROLE_BOUTIQUE,
            entreprise=cls.ent, lieu=cls.boutique2,
        )
        cls.user_admin = CustomUser.objects.create_user(
            username="admin_c", password="x", role=CustomUser.ROLE_ADMIN,
            entreprise=cls.ent,
        )
        cls.user_comptable = CustomUser.objects.create_user(
            username="cpt_c", password="x", role=CustomUser.ROLE_COMPTABLE,
            entreprise=cls.ent,
        )
        cls.user_usine = CustomUser.objects.create_user(
            username="usine_c", password="x", role=CustomUser.ROLE_USINE,
            entreprise=cls.ent,
        )

        # Autre entreprise pour tests isolation
        cls.ent2 = Entreprise.objects.create(nom="Autre Ent")
        cls.lieu2 = Lieu.objects.create(
            entreprise=cls.ent2, nom="Boutique Autre", type_lieu=Lieu.TYPE_MAGASIN, code="BA"
        )
        cls.user_admin2 = CustomUser.objects.create_user(
            username="admin2_c", password="x", role=CustomUser.ROLE_ADMIN,
            entreprise=cls.ent2, lieu=cls.lieu2,
        )

        # Produit + stock pour tests auto-upgrade
        cat = Categorie.objects.create(nom="Farine", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            categorie=cat, nom="Farine 50kg", code="F50", unite="sac",
            entreprise=cls.ent,
        )
        Stock.objects.create(produit=cls.produit, lieu=cls.boutique, quantite=Decimal("100"))

    URL_BOUTIQUE = "boutique-clients"
    URL_ADMIN    = "admin-clients"


# ── A–E : POST /boutique/clients/ ─────────────────────────────────────────────

class TestCreationClient(_Base):

    def test_A_creation_prospect_avec_lieu(self):
        """Création d'un visiteur : statut=prospect, lieu enregistré."""
        r = self.client.post(
            reverse(self.URL_BOUTIQUE),
            {"nom": "Mamadou Diallo", "contact": "0700000000", "interet": "farine 50kg", "statut": "prospect"},
            format="json",
            **_auth(self.user_boutique),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        c = ClientFinance.objects.get(nom__iexact="Mamadou Diallo", entreprise=self.ent)
        self.assertEqual(c.statut, ClientFinance.STATUT_PROSPECT)
        self.assertEqual(c.lieu_id, self.boutique.pk)
        self.assertEqual(c.interet, "farine 50kg")

    def test_B_creation_client_explicite(self):
        """statut=client est respecté."""
        r = self.client.post(
            reverse(self.URL_BOUTIQUE),
            {"nom": "Fatoumata Koné", "statut": "client"},
            format="json",
            **_auth(self.user_boutique),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.json()["statut"], "client")

    def test_C_idempotence_nom_existant(self):
        """Même nom (insensible casse) → 200 + client existant retourné."""
        ClientFinance.objects.create(
            entreprise=self.ent, nom="Ibrahim Traoré", statut=ClientFinance.STATUT_PROSPECT
        )
        r = self.client.post(
            reverse(self.URL_BOUTIQUE),
            {"nom": "ibrahim traoré"},
            format="json",
            **_auth(self.user_boutique),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(ClientFinance.objects.filter(nom__iexact="Ibrahim Traoré", entreprise=self.ent).count(), 1)

    def test_D_comptable_peut_creer(self):
        """Le comptable a le droit de créer un visiteur."""
        r = self.client.post(
            reverse(self.URL_BOUTIQUE),
            {"nom": "Koffi Atta", "statut": "prospect"},
            format="json",
            **_auth(self.user_comptable),
        )
        self.assertIn(r.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

    def test_E_role_usine_interdit(self):
        """Un utilisateur usine ne peut pas accéder à l'endpoint boutique/clients."""
        r = self.client.post(
            reverse(self.URL_BOUTIQUE),
            {"nom": "Test"},
            format="json",
            **_auth(self.user_usine),
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


# ── F : Auto-upgrade prospect → client ────────────────────────────────────────

class TestAutoUpgrade(_Base):

    def test_F_prospect_devient_client_a_lachat(self):
        """Prospect lié à un achat → statut passe à client."""
        prospect = ClientFinance.objects.create(
            entreprise=self.ent, nom="Sékou Bah",
            statut=ClientFinance.STATUT_PROSPECT, lieu=self.boutique,
        )
        r = self.client.post(
            reverse("boutique-ventes-list"),
            {
                "client_id": prospect.pk,
                "lignes": [{"produit": self.produit.pk, "quantite": 1, "prix_unitaire": 100}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="autoupgrade-test-1",
            **_auth(self.user_boutique),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        prospect.refresh_from_db()
        self.assertEqual(prospect.statut, ClientFinance.STATUT_CLIENT)

    def test_F2_client_reste_client(self):
        """Un client existant reste client après un nouvel achat."""
        client = ClientFinance.objects.create(
            entreprise=self.ent, nom="Ami Coulibaly",
            statut=ClientFinance.STATUT_CLIENT, lieu=self.boutique,
        )
        r = self.client.post(
            reverse("boutique-ventes-list"),
            {
                "client_id": client.pk,
                "lignes": [{"produit": self.produit.pk, "quantite": 1, "prix_unitaire": 100}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="autoupgrade-test-2",
            **_auth(self.user_boutique),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        client.refresh_from_db()
        self.assertEqual(client.statut, ClientFinance.STATUT_CLIENT)


# ── G–M : GET /admin/clients/ ─────────────────────────────────────────────────

class TestAdminClientsView(_Base):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Clients de référence
        cls.prospect_nord = ClientFinance.objects.create(
            entreprise=cls.ent, nom="Prospect Nord",
            statut=ClientFinance.STATUT_PROSPECT, lieu=cls.boutique,
            interet="huile de palme",
        )
        cls.client_sud = ClientFinance.objects.create(
            entreprise=cls.ent, nom="Client Sud",
            statut=ClientFinance.STATUT_CLIENT, lieu=cls.boutique2,
        )
        cls.client_autre_ent = ClientFinance.objects.create(
            entreprise=cls.ent2, nom="Client Autre",
            statut=ClientFinance.STATUT_CLIENT, lieu=cls.lieu2,
        )

    def _get(self, user, params=""):
        return self.client.get(
            reverse(self.URL_ADMIN) + (f"?{params}" if params else ""),
            **_auth(user),
        )

    def test_G_admin_voit_ses_clients_avec_lieu_nom(self):
        """Admin voit tous les clients de son entreprise avec lieu_nom."""
        r = self._get(self.user_admin)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        noms = [c["nom"] for c in r.json()]
        self.assertIn("Prospect Nord", noms)
        self.assertIn("Client Sud", noms)
        self.assertNotIn("Client Autre", noms)
        # lieu_nom présent
        nord = next(c for c in r.json() if c["nom"] == "Prospect Nord")
        self.assertEqual(nord["lieu_nom"], "Boutique Nord")

    def test_H_filtre_statut_prospect(self):
        """?statut=prospect ne retourne que les prospects."""
        r = self._get(self.user_admin, "statut=prospect")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        statuts = {c["statut"] for c in r.json()}
        self.assertEqual(statuts, {"prospect"})

    def test_H2_filtre_statut_client(self):
        """?statut=client ne retourne que les clients."""
        r = self._get(self.user_admin, "statut=client")
        statuts = {c["statut"] for c in r.json()}
        self.assertEqual(statuts, {"client"})

    def test_I_filtre_lieu(self):
        """?lieu=<id> ne retourne que les clients de cette boutique."""
        r = self._get(self.user_admin, f"lieu={self.boutique.pk}")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        noms = [c["nom"] for c in r.json()]
        self.assertIn("Prospect Nord", noms)
        self.assertNotIn("Client Sud", noms)

    def test_I2_filtre_lieu_invalide_400(self):
        """?lieu=abc → 400."""
        r = self._get(self.user_admin, "lieu=abc")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_J_filtre_search(self):
        """?search=palme retrouve via le champ interet."""
        r = self._get(self.user_admin, "search=palme")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        noms = [c["nom"] for c in r.json()]
        self.assertIn("Prospect Nord", noms)
        self.assertNotIn("Client Sud", noms)

    def test_K_comptable_peut_acceder(self):
        """Le comptable peut lire /admin/clients/."""
        r = self._get(self.user_comptable)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_L_boutique_ne_peut_pas_acceder(self):
        """Un rôle boutique ne peut pas accéder à /admin/clients/ (403)."""
        r = self._get(self.user_boutique)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_M_isolation_tenant(self):
        """Admin d'une autre entreprise ne voit pas les clients de cette entreprise."""
        r = self._get(self.user_admin2)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        noms = [c["nom"] for c in r.json()]
        self.assertNotIn("Prospect Nord", noms)
        self.assertNotIn("Client Sud", noms)
        self.assertIn("Client Autre", noms)
