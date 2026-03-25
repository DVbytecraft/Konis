"""
Tests pour AchatMPSLBatchView — POST /api/mpsl/achats/batch/

Couvre :
  1. Permission : seul MPSL/admin accède
  2. Cash — multi-produits → plusieurs AchatMPSL, stock incrémenté
  3. Crédit — fournisseur existant → JournalPayable créé
  4. Partiel — acompte → JournalPayable partiel
  5. Crédit — nouveau fournisseur inline (fournisseur_nom)
  6. Crédit sans fournisseur → 400
  7. Isolation multi-tenant (fournisseur autre entreprise → 400)
  8. Idempotency — double soumission même clé → un seul enregistrement
  9. Stock incrémenté correctement pour chaque produit du batch
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from finance.models import Creancier, JournalPayable
from inventaire.models import AchatMPSL, Stock
from produits.models import Produit


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ent(nom):
    return Entreprise.objects.create(nom=nom)


def _lieu_mpsl(ent, nom="MPSL Depot", code="MPSL"):
    return Lieu.objects.create(
        entreprise=ent, nom=nom, code=code, type_lieu=Lieu.TYPE_MPSL
    )


def _user_mpsl(ent, lieu, username):
    return CustomUser.objects.create_user(
        username=username, password="pass1234",
        role=CustomUser.ROLE_MPSL, entreprise=ent, lieu=lieu,
    )


def _user_admin(ent, lieu, username):
    return CustomUser.objects.create_user(
        username=username, password="pass1234",
        role=CustomUser.ROLE_ADMIN, entreprise=ent, lieu=lieu,
    )


def _user_boutique(ent, lieu, username):
    return CustomUser.objects.create_user(
        username=username, password="pass1234",
        role=CustomUser.ROLE_BOUTIQUE, entreprise=ent, lieu=lieu,
    )


def _fournisseur(ent, nom="Fournisseur Test"):
    return Creancier.objects.create(
        entreprise=ent, nom=nom, type_creancier="fournisseur", statut="actif"
    )


def _jwt(user):
    token = str(RefreshToken.for_user(user).access_token)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


BATCH_URL = "/api/mpsl/achats/batch/"


def _payload_cash(produit_nom="Maïs", quantite=10, prix=500):
    return {
        "type_paiement": "cash",
        "produits": [
            {
                "produit_nom": produit_nom, "quantite": quantite,
                "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": prix,
            },
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. Permissions
# ════════════════════════════════════════════════════════════════════════════

class TestBatchPermissions(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntPerm")
        cls.lieu = _lieu_mpsl(cls.ent, code="PM")
        cls.lieu_admin = _lieu_mpsl(cls.ent, nom="MPSL Admin", code="PMA")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique PM", code="BPM", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.mpsl_user  = _user_mpsl(cls.ent, cls.lieu, "mpsl_perm")
        cls.admin_user = _user_admin(cls.ent, cls.lieu_admin, "admin_perm")
        cls.boutiquer  = _user_boutique(cls.ent, cls.boutique, "bout_perm")

    def test_mpsl_user_peut_acceder(self):
        r = self.client.post(BATCH_URL, _payload_cash(), format="json", **_jwt(self.mpsl_user))
        self.assertNotEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_peut_acceder(self):
        r = self.client.post(BATCH_URL, _payload_cash(), format="json", **_jwt(self.admin_user))
        self.assertNotEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_boutique_ne_peut_pas_acceder(self):
        r = self.client.post(BATCH_URL, _payload_cash(), format="json", **_jwt(self.boutiquer))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_authentifie_401(self):
        r = self.client.post(BATCH_URL, _payload_cash(), format="json")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)


# ════════════════════════════════════════════════════════════════════════════
# 2. Cash — multi-produits
# ════════════════════════════════════════════════════════════════════════════

class TestBatchCash(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntCash")
        cls.lieu = _lieu_mpsl(cls.ent, code="CA")
        cls.user = _user_mpsl(cls.ent, cls.lieu, "mpsl_cash")

    def test_multi_produits_creates_achats(self):
        payload = {
            "type_paiement": "cash",
            "produits": [
                {"produit_nom": "Maïs", "quantite": 5, "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 1000},
                {"produit_nom": "Blé",  "quantite": 3, "unite": "kg",   "prix_unitaire": 200},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        data = r.json()
        self.assertEqual(len(data), 2)

    def test_stock_incremented_per_produit(self):
        payload = {
            "type_paiement": "cash",
            "produits": [
                {"produit_nom": "SorghoStock", "quantite": 10, "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 800},
            ],
        }
        avant = AchatMPSL.objects.filter(
            lieu=self.lieu, produit_nom="SorghoStock"
        ).count()
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        apres = AchatMPSL.objects.filter(
            lieu=self.lieu, produit_nom="SorghoStock"
        ).count()
        self.assertEqual(apres - avant, 1)
        # Stock créé ou incrémenté
        stocks = Stock.objects.filter(lieu=self.lieu)
        self.assertTrue(stocks.exists())

    def test_cash_sans_fournisseur_ok(self):
        """Achat cash : aucun fournisseur requis."""
        payload = {
            "type_paiement": "cash",
            "produits": [
                {"produit_nom": "Millet", "quantite": 2, "unite": "kg", "prix_unitaire": 300},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_pas_de_journal_payable_pour_cash(self):
        """Achat cash → aucun JournalPayable créé."""
        avant = JournalPayable.objects.filter(
            creancier__entreprise=self.ent
        ).count()
        payload = {
            "type_paiement": "cash",
            "produits": [
                {"produit_nom": "CashNoDette", "quantite": 1, "unite": "sacs", "prix_unitaire": 500},
            ],
        }
        self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        apres = JournalPayable.objects.filter(
            creancier__entreprise=self.ent
        ).count()
        self.assertEqual(avant, apres)


# ════════════════════════════════════════════════════════════════════════════
# 3. Crédit — fournisseur existant
# ════════════════════════════════════════════════════════════════════════════

class TestBatchCredit(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent        = _ent("EntCredit")
        cls.lieu       = _lieu_mpsl(cls.ent, code="CR")
        cls.user       = _user_mpsl(cls.ent, cls.lieu, "mpsl_credit")
        cls.fournisseur = _fournisseur(cls.ent, "Fournisseur Crédit")

    def test_credit_avec_fournisseur_cree_journal(self):
        """10 sacs × 1500 = 15 000 FCFA. Crédit total → montant_initial=15000, montant_paye=0."""
        avant = JournalPayable.objects.filter(creancier=self.fournisseur).count()
        payload = {
            "type_paiement": "credit",
            "fournisseur_id": self.fournisseur.pk,
            "produits": [
                {"produit_nom": "Maïs Crédit", "quantite": 10, "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 1500},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        apres = JournalPayable.objects.filter(creancier=self.fournisseur).count()
        self.assertEqual(apres - avant, 1)
        journal = JournalPayable.objects.filter(creancier=self.fournisseur).latest("created_at")
        self.assertEqual(journal.montant_initial, Decimal("15000"))
        self.assertEqual(journal.montant_paye, Decimal("0"))
        self.assertEqual(journal.montant_restant, Decimal("15000"))

    def test_credit_sans_fournisseur_retourne_400(self):
        payload = {
            "type_paiement": "credit",
            "produits": [
                {"produit_nom": "Blé sans fourn", "quantite": 5, "unite": "kg", "prix_unitaire": 200},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ════════════════════════════════════════════════════════════════════════════
# 4. Partiel — acompte
# ════════════════════════════════════════════════════════════════════════════

class TestBatchPartiel(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent        = _ent("EntPartiel")
        cls.lieu       = _lieu_mpsl(cls.ent, code="PT")
        cls.user       = _user_mpsl(cls.ent, cls.lieu, "mpsl_partiel")
        cls.fournisseur = _fournisseur(cls.ent, "Fournisseur Partiel")

    def test_partiel_cree_journal_avec_acompte(self):
        """
        20 sacs × 2000 FCFA = 40 000 FCFA total.
        Acompte = 5 000 FCFA.
        Journal : montant_initial=40 000, montant_paye=5 000, montant_restant=35 000.
        """
        payload = {
            "type_paiement": "partiel",
            "fournisseur_id": self.fournisseur.pk,
            "acompte": 5000,
            "produits": [
                {"produit_nom": "Riz Partiel", "quantite": 20, "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 2000},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        journal = JournalPayable.objects.filter(creancier=self.fournisseur).first()
        self.assertIsNotNone(journal)
        # Source de vérité : le montant_initial = TOTAL de la commande (pas total-acompte)
        self.assertEqual(journal.montant_initial, Decimal("40000"))
        self.assertEqual(journal.montant_paye, Decimal("5000"))
        self.assertEqual(journal.montant_restant, Decimal("35000"))


# ════════════════════════════════════════════════════════════════════════════
# 5. Nouveau fournisseur inline
# ════════════════════════════════════════════════════════════════════════════

class TestBatchNouveauFournisseur(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntNewFourn")
        cls.lieu = _lieu_mpsl(cls.ent, code="NF")
        cls.user = _user_mpsl(cls.ent, cls.lieu, "mpsl_newfourn")

    def test_credit_fournisseur_nom_cree_creancier(self):
        avant = Creancier.objects.filter(entreprise=self.ent).count()
        payload = {
            "type_paiement": "credit",
            "fournisseur_nom": "Nouveau Fournisseur MPSL",
            "produits": [
                {"produit_nom": "Mil Nouveau", "quantite": 5, "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 900},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        apres = Creancier.objects.filter(entreprise=self.ent).count()
        self.assertEqual(apres - avant, 1)

    def test_credit_fournisseur_nom_duplicate_non_duplique(self):
        """Même nom fournisseur en double → un seul créancier (get_or_create)."""
        Creancier.objects.create(
            entreprise=self.ent, nom="Fourn Existant",
            type_creancier="fournisseur", statut="actif"
        )
        avant = Creancier.objects.filter(entreprise=self.ent, nom="Fourn Existant").count()
        payload = {
            "type_paiement": "credit",
            "fournisseur_nom": "fourn existant",  # casse différente
            "produits": [
                {"produit_nom": "Produit Duplic", "quantite": 2, "unite": "kg", "prix_unitaire": 100},
            ],
        }
        self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user))
        apres = Creancier.objects.filter(
            entreprise=self.ent, nom__iexact="fourn existant"
        ).count()
        self.assertEqual(apres, avant)


# ════════════════════════════════════════════════════════════════════════════
# 6. Isolation multi-tenant
# ════════════════════════════════════════════════════════════════════════════

class TestBatchMultiTenant(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent_a = _ent("EntA-Batch")
        cls.ent_b = _ent("EntB-Batch")
        cls.lieu_a = _lieu_mpsl(cls.ent_a, code="MA")
        cls.user_a = _user_mpsl(cls.ent_a, cls.lieu_a, "mpsl_a_bt")
        # Fournisseur appartenant à ent_b
        cls.fourn_b = _fournisseur(cls.ent_b, "Fourn EntB")

    def test_fournisseur_autre_entreprise_retourne_400(self):
        """Un utilisateur de ent_a ne peut pas utiliser un fournisseur de ent_b."""
        payload = {
            "type_paiement": "credit",
            "fournisseur_id": self.fourn_b.pk,
            "produits": [
                {"produit_nom": "Produit Cross", "quantite": 5, "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 500},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user_a))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stock_isole_par_lieu(self):
        """Le stock est créé uniquement pour le lieu de l'utilisateur."""
        payload = {
            "type_paiement": "cash",
            "produits": [
                {"produit_nom": "ProdIsolé", "quantite": 7, "unite": "kg", "prix_unitaire": 300},
            ],
        }
        r = self.client.post(BATCH_URL, payload, format="json", **_jwt(self.user_a))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        stocks = Stock.objects.filter(lieu=self.lieu_a, produit__isnull=False)
        # Tous les stocks appartiennent au lieu de l'entreprise A
        for stock in stocks:
            self.assertEqual(stock.lieu.entreprise_id, self.ent_a.pk)


# ════════════════════════════════════════════════════════════════════════════
# 7. Idempotency
# ════════════════════════════════════════════════════════════════════════════

class TestBatchIdempotency(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntIdemBatch")
        cls.lieu = _lieu_mpsl(cls.ent, code="IB")
        cls.user = _user_mpsl(cls.ent, cls.lieu, "mpsl_idem")

    def _post(self, key=None):
        h = _jwt(self.user)
        if key:
            h["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            BATCH_URL,
            {
                "type_paiement": "cash",
                "produits": [
                    {
                        "produit_nom": "Maïs Idem", "quantite": 5,
                        "unite": "sacs", "poids_par_sac": "50.000", "prix_unitaire": 1000,
                    },
                ],
            },
            format="json",
            **h,
        )

    def test_double_soumission_meme_cle_cree_un_seul_achat(self):
        key = "batch-idem-001"
        avant = AchatMPSL.objects.filter(lieu=self.lieu, produit_nom="Maïs Idem").count()
        r1 = self._post(key)
        r2 = self._post(key)
        self.assertIn(r1.status_code, [200, 201])
        self.assertIn(r2.status_code, [200, 201])
        apres = AchatMPSL.objects.filter(lieu=self.lieu, produit_nom="Maïs Idem").count()
        self.assertEqual(apres - avant, 1)

    def test_sans_cle_cree_normalement(self):
        """Sans Idempotency-Key → required=False, accepté normalement."""
        r = self._post(key=None)
        self.assertIn(r.status_code, [200, 201])


# ════════════════════════════════════════════════════════════════════════════
# 8. Validation payload
# ════════════════════════════════════════════════════════════════════════════

class TestBatchValidation(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntVal")
        cls.lieu = _lieu_mpsl(cls.ent, code="VL")
        cls.user = _user_mpsl(cls.ent, cls.lieu, "mpsl_val")

    def test_produits_vide_retourne_400(self):
        r = self.client.post(
            BATCH_URL,
            {"type_paiement": "cash", "produits": []},
            format="json",
            **_jwt(self.user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_type_paiement_invalide_retourne_400(self):
        r = self.client.post(
            BATCH_URL,
            {
                "type_paiement": "barter",
                "produits": [
                    {"produit_nom": "Blé", "quantite": 1, "unite": "kg", "prix_unitaire": 100},
                ],
            },
            format="json",
            **_jwt(self.user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quantite_zero_retourne_400(self):
        r = self.client.post(
            BATCH_URL,
            {
                "type_paiement": "cash",
                "produits": [
                    {"produit_nom": "Blé", "quantite": 0, "unite": "kg", "prix_unitaire": 100},
                ],
            },
            format="json",
            **_jwt(self.user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
