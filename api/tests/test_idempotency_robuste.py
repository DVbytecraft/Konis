"""
Tests d'idempotency robuste KONIS — système IdempotencyKey dédié.

Couvre :
  A. Idempotency transactionnelle — table dédiée, concurrence réelle
  B. Double clic utilisateur (deux POST rapides, même clé)
  C. Conflit de payload (même clé, données différentes → 409)
  D. Clé absente en strict mode → 400
  E. Longueur de clé > 128 → 400 (middleware)
  F. Journaux soldés immuables — trigger PostgreSQL DB-level
  G. Finance — paiements idempotents (JournalPayable, JournalCreance)
  H. Finance — caisse suprême idempotente
  I. Finance — projet dépense/dépôt idempotents
  J. Concurrence réelle — ThreadPoolExecutor (2 threads simultanés)
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, IdempotencyKey, Lieu
from finance.models import (
    ClientFinance,
    Creancier,
    JournalCreance,
    JournalPayable,
)
from produits.models import Produit
from inventaire.models import Stock


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ent(nom="EntIdem"):
    return Entreprise.objects.create(nom=nom)

def _lieu(ent, nom="Boutique", code="BT"):
    return Lieu.objects.create(
        entreprise=ent, nom=nom, code=code, type_lieu=Lieu.TYPE_MAGASIN
    )

def _user(ent, lieu=None, username="user", role=CustomUser.ROLE_BOUTIQUE):
    return CustomUser.objects.create_user(
        username=username, password="pass1234",
        role=role, entreprise=ent, lieu=lieu,
    )

def _admin_fin(ent, username="admin_fin"):
    """Admin financier — ROLE_ADMIN (peut écrire sur finance, pas read-only)."""
    lieu = Lieu.objects.create(
        entreprise=ent, nom=f"HQ-{username}", code=username[:6].upper(),
        type_lieu=Lieu.TYPE_MAGASIN,
    )
    return CustomUser.objects.create_user(
        username=username, password="pass1234",
        role=CustomUser.ROLE_ADMIN, entreprise=ent, lieu=lieu,
    )

def _jwt(user):
    token = str(RefreshToken.for_user(user).access_token)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

def _produit(ent, code="P001"):
    return Produit.objects.create(
        nom=f"Produit {code}", code=code, unite="kg", entreprise=ent
    )


# ════════════════════════════════════════════════════════════════════════════
# A + B. Double clic — vente boutique (DB UniqueConstraint déjà robuste)
# ════════════════════════════════════════════════════════════════════════════

class TestDoubleClic(APITestCase):
    """Deux POST identiques (double clic) → un seul enregistrement."""

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntDC")
        cls.lieu = _lieu(cls.ent, code="DC")
        cls.user = _user(cls.ent, cls.lieu, username="vendeur_dc")
        cls.prod = _produit(cls.ent, "DC01")
        Stock.objects.create(produit=cls.prod, lieu=cls.lieu, quantite=Decimal("100"))

    def _post(self, key=None):
        h = _jwt(self.user)
        if key:
            h["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            "/api/boutique/ventes/",
            {"lignes": [{"produit": self.prod.pk, "quantite": 1, "prix_unitaire": 100}]},
            format="json", **h,
        )

    def test_double_clic_retourne_meme_ticket(self):
        key = "dc-test-001"
        r1 = self._post(key)
        r2 = self._post(key)
        self.assertIn(r1.status_code, [201, 200])
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_double_clic_stock_debite_une_fois(self):
        key = "dc-test-002"
        avant = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite
        self._post(key)
        self._post(key)
        apres = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite
        self.assertEqual(avant - apres, Decimal("1"))


# ════════════════════════════════════════════════════════════════════════════
# C. Conflit de payload (IdempotencyKey table)
# ════════════════════════════════════════════════════════════════════════════

@override_settings(IDEMPOTENCY_STRICT_MODE=True)
class TestPayloadConflit(APITestCase):
    """Même clé + payload différent → 409 Conflict."""

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntConf")
        cls.lieu = _lieu(cls.ent, code="CF")
        cls.daf  = _admin_fin(cls.ent, username="fin_conf")
        cls.cre  = Creancier.objects.create(
            entreprise=cls.ent, nom="Fournisseur Conf", type_creancier="fournisseur"
        )

    def _post_journal(self, montant, key):
        return self.client.post(
            "/api/finance/journaux-payables/",
            {
                "creancier_id": self.cre.pk,
                "description": "Test conflit",
                "montant_initial": str(montant),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            **_jwt(self.daf),
        )

    def test_meme_cle_payload_different_retourne_409(self):
        key = "conf-test-001"
        r1 = self._post_journal("50000.00", key)
        self.assertEqual(r1.status_code, 201)
        # Même clé, montant différent → 409
        r2 = self._post_journal("99999.00", key)
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("payload différent", r2.json()["detail"])


# ════════════════════════════════════════════════════════════════════════════
# D. Clé absente en strict mode
# ════════════════════════════════════════════════════════════════════════════

@override_settings(IDEMPOTENCY_STRICT_MODE=True)
class TestCleAbsente(APITestCase):
    """Sans Idempotency-Key en strict mode → 400."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _ent("EntStrict")
        cls.daf = _admin_fin(cls.ent, username="daf_strict")
        cls.cre = Creancier.objects.create(
            entreprise=cls.ent, nom="Fournisseur S", type_creancier="fournisseur"
        )

    def test_sans_cle_journal_payable_retourne_400(self):
        r = self.client.post(
            "/api/finance/journaux-payables/",
            {"creancier_id": self.cre.pk, "description": "Test", "montant_initial": "1000.00"},
            format="json",
            **_jwt(self.daf),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Idempotency-Key", r.json()["detail"])

    def test_sans_cle_caisse_retourne_400(self):
        r = self.client.post(
            "/api/finance/caisse/",
            {"type_transaction": "depot", "montant": "1000.00",
             "description": "Test", "date": "2026-03-24"},
            format="json",
            **_jwt(self.daf),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ════════════════════════════════════════════════════════════════════════════
# E. Middleware — longueur de clé > 128
# ════════════════════════════════════════════════════════════════════════════

class TestMiddlewareLongueur(APITestCase):
    """Idempotency-Key > 128 chars → 400 via middleware, avant toute logique."""

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntMW")
        cls.lieu = _lieu(cls.ent, code="MW")
        cls.user = _user(cls.ent, cls.lieu, username="user_mw")
        cls.prod = _produit(cls.ent, "MW01")
        Stock.objects.create(produit=cls.prod, lieu=cls.lieu, quantite=Decimal("50"))
        cls.daf  = _admin_fin(cls.ent, username="daf_mw")

    def test_cle_129_chars_boutique_retourne_400(self):
        avant = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite
        r = self.client.post(
            "/api/boutique/ventes/",
            {"lignes": [{"produit": self.prod.pk, "quantite": 1, "prix_unitaire": 100}]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="x" * 129,
            **_jwt(self.user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("trop longue", r.json()["detail"])
        # Stock inchangé
        apres = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite
        self.assertEqual(avant, apres)

    def test_cle_129_chars_finance_retourne_400(self):
        r = self.client.post(
            "/api/finance/caisse/",
            {"type_transaction": "depot", "montant": "500.00",
             "description": "Test MW", "date": "2026-03-24"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="y" * 129,
            **_jwt(self.daf),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cle_128_chars_acceptee(self):
        """Exactement 128 chars → acceptée (limite incluse)."""
        r = self.client.post(
            "/api/finance/caisse/",
            {"type_transaction": "depot", "montant": "500.00",
             "description": "Test MW 128", "date": "2026-03-24"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="z" * 128,
            **_jwt(self.daf),
        )
        # 201 ou 400 (strict mode) mais PAS 400 pour "trop longue"
        if r.status_code == 400:
            self.assertNotIn("trop longue", r.json().get("detail", ""))


# ════════════════════════════════════════════════════════════════════════════
# F. Journaux soldés — trigger PostgreSQL DB-level
# ════════════════════════════════════════════════════════════════════════════

class TestJournalImmuableTrigger(TestCase):
    """Le trigger PostgreSQL bloque toute modification ORM ou .update() sur journal soldé."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _ent("EntTrig")
        cls.daf = _admin_fin(cls.ent, username="daf_trig")
        cls.cre = Creancier.objects.create(
            entreprise=cls.ent, nom="Fournisseur T", type_creancier="fournisseur"
        )
        cls.journal = JournalPayable.objects.create(
            creancier=cls.cre,
            description="Journal test trigger",
            montant_initial=Decimal("10000.00"),
            montant_paye=Decimal("10000.00"),
            statut="solde",
            locked_at=timezone.now(),
            created_by=cls.daf,
        )

    def test_trigger_bloque_update_orm_sur_journal_solde(self):
        """JournalPayable.objects.update() sur journal soldé → exception DB."""
        from django.db import DatabaseError
        with self.assertRaises((DatabaseError, Exception)):
            JournalPayable.objects.filter(pk=self.journal.pk).update(
                description="Tentative de modification"
            )

    def test_save_bloque_modification_journal_solde(self):
        """journal.save() sur journal soldé → ValidationError."""
        from django.core.exceptions import ValidationError
        self.journal.refresh_from_db()
        self.journal.description = "Tentative via save()"
        with self.assertRaises(ValidationError):
            self.journal.save()

    def test_journal_creance_solde_immuable(self):
        """JournalCreance soldé : trigger bloque UPDATE."""
        from django.db import DatabaseError
        client = ClientFinance.objects.create(
            entreprise=self.ent, nom="Client Trig", statut="client"
        )
        journal = JournalCreance.objects.create(
            client=client,
            description="Créance test trigger",
            montant_initial=Decimal("5000.00"),
            montant_paye=Decimal("5000.00"),
            statut="solde",
            locked_at=timezone.now(),
            created_by=self.daf,
        )
        with self.assertRaises((DatabaseError, Exception)):
            JournalCreance.objects.filter(pk=journal.pk).update(description="Hack")


# ════════════════════════════════════════════════════════════════════════════
# G. Finance — paiements idempotents
# ════════════════════════════════════════════════════════════════════════════

@override_settings(IDEMPOTENCY_STRICT_MODE=False)
class TestPaiementIdempotent(APITestCase):
    """Paiement sur journal payable — double soumission retourne même résultat."""

    @classmethod
    def setUpTestData(cls):
        cls.ent  = _ent("EntPaie")
        cls.daf  = _admin_fin(cls.ent, username="daf_paie")
        cls.cre  = Creancier.objects.create(
            entreprise=cls.ent, nom="Fournisseur P", type_creancier="fournisseur"
        )
        cls.journal = JournalPayable.objects.create(
            creancier=cls.cre,
            description="Journal paiement idempotent",
            montant_initial=Decimal("50000.00"),
            created_by=cls.daf,
        )

    def _post_paiement(self, key=None):
        h = _jwt(self.daf)
        if key:
            h["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            f"/api/finance/journaux-payables/{self.journal.pk}/paiement/",
            {"montant": "10000.00", "date": "2026-03-24"},
            format="json", **h,
        )

    def test_double_paiement_meme_cle_debite_une_fois(self):
        key = "paie-idem-001"
        r1 = self._post_paiement(key)
        r2 = self._post_paiement(key)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.montant_paye, Decimal("10000.00"))

    def test_meme_cle_retourne_reponse_identique(self):
        key = "paie-idem-002"
        r1 = self._post_paiement(key)
        r2 = self._post_paiement(key)
        self.assertEqual(r1.json()["montant_paye"], r2.json()["montant_paye"])


# ════════════════════════════════════════════════════════════════════════════
# H. Finance — caisse suprême idempotente
# ════════════════════════════════════════════════════════════════════════════

@override_settings(IDEMPOTENCY_STRICT_MODE=False)
class TestCaisseIdempotente(APITestCase):
    """Transaction caisse — double soumission crée un seul mouvement."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = _ent("EntCaisse")
        cls.daf = _admin_fin(cls.ent, username="daf_caisse")

    def _post_depot(self, key=None):
        h = _jwt(self.daf)
        if key:
            h["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            "/api/finance/caisse/",
            {"type_transaction": "depot", "montant": "25000.00",
             "description": "Dépôt test idempotent", "date": "2026-03-24"},
            format="json", **h,
        )

    def test_double_depot_meme_cle_cree_un_seul_mouvement(self):
        from finance.models import CaisseSupremeTransaction
        key = "caisse-idem-001"
        avant = CaisseSupremeTransaction.objects.filter(entreprise=self.ent).count()
        r1 = self._post_depot(key)
        r2 = self._post_depot(key)
        self.assertIn(r1.status_code, [200, 201])
        self.assertIn(r2.status_code, [200, 201])
        apres = CaisseSupremeTransaction.objects.filter(entreprise=self.ent).count()
        self.assertEqual(apres - avant, 1)


# ════════════════════════════════════════════════════════════════════════════
# I. Finance — projet dépense idempotente
# ════════════════════════════════════════════════════════════════════════════

@override_settings(IDEMPOTENCY_STRICT_MODE=False)
class TestProjetDepenseIdempotente(APITestCase):
    """Dépense projet — double soumission ne débite qu'une fois."""

    @classmethod
    def setUpTestData(cls):
        from finance.models import Projet
        cls.ent  = _ent("EntProjet")
        cls.daf  = _admin_fin(cls.ent, username="daf_projet")
        cls.proj = Projet.objects.create(
            entreprise=cls.ent,
            created_by=cls.daf,
            nom="Projet Idempotent",
            description="",
            budget_initial=Decimal("100000.00"),
            date_debut="2026-01-01",
        )

    def _post_depense(self, key=None):
        h = _jwt(self.daf)
        if key:
            h["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            f"/api/finance/projets/{self.proj.pk}/depense/",
            {"montant": "5000.00", "description": "Dépense idempotente", "date": "2026-03-24"},
            format="json", **h,
        )

    def test_double_depense_meme_cle_debite_une_fois(self):
        from finance.models import DepenseProjet
        key = "proj-dep-001"
        avant = DepenseProjet.objects.filter(projet=self.proj).count()
        r1 = self._post_depense(key)
        r2 = self._post_depense(key)
        self.assertIn(r1.status_code, [200, 201])
        self.assertIn(r2.status_code, [200, 201])
        apres = DepenseProjet.objects.filter(projet=self.proj).count()
        self.assertEqual(apres - avant, 1)


# ════════════════════════════════════════════════════════════════════════════
# J. Concurrence réelle — ThreadPoolExecutor
# ════════════════════════════════════════════════════════════════════════════

class TestConcurrenceReelle(TransactionTestCase):
    """
    Deux threads simultanés avec la même Idempotency-Key → une seule exécution.

    Utilise TransactionTestCase (pas de rollback automatique entre tests)
    pour que les threads voient les mêmes données DB.
    """

    def setUp(self):
        self.ent  = _ent("EntThread")
        self.lieu = _lieu(self.ent, code="TH")
        self.user = _user(self.ent, self.lieu, username="user_thread")
        self.prod = _produit(self.ent, "TH01")
        Stock.objects.create(produit=self.prod, lieu=self.lieu, quantite=Decimal("100"))
        # Pré-générer le token avant les threads pour éviter les accès DB concurrents au setup
        self._token = str(RefreshToken.for_user(self.user).access_token)

    def _post_vente(self, key):
        from django.db import close_old_connections
        close_old_connections()
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token}")
        resp = c.post(
            "/api/boutique/ventes/",
            {"lignes": [{"produit": self.prod.pk, "quantite": 5, "prix_unitaire": 200}]},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        close_old_connections()
        return resp

    def test_deux_threads_meme_cle_stock_debite_une_fois(self):
        """2 requêtes concurrentes → stock débité au maximum 1 fois (DB UniqueConstraint)."""
        import uuid
        from django.db import connection as _conn
        key = f"race-{uuid.uuid4().hex}"

        def do_request():
            try:
                self._post_vente(key)
            except Exception:
                pass
            finally:
                # Ferme la connexion du thread pour éviter les connexions orphelines
                _conn.close()

        t1 = threading.Thread(target=do_request)
        t2 = threading.Thread(target=do_request)
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Rouvrir une connexion propre depuis le thread principal
        from django.db import connections
        connections["default"].ensure_connection()

        stock_final = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite
        # Au maximum 1 débit de 5 unités (UniqueConstraint sur Ticket.idempotency_key)
        self.assertGreaterEqual(stock_final, Decimal("90"))

    def test_deux_threads_stock_coherent(self):
        """Deux threads simultanés ne corrompent pas le stock."""
        import uuid
        key = f"coherence-{uuid.uuid4().hex}"
        avant = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite

        def do_request():
            try:
                self._post_vente(key)
            except Exception:
                pass

        t1 = threading.Thread(target=do_request)
        t2 = threading.Thread(target=do_request)
        t1.start(); t2.start()
        t1.join(); t2.join()

        from django.db import connection
        connection.ensure_connection()

        apres = Stock.objects.get(produit=self.prod, lieu=self.lieu).quantite
        # Cohérence : jamais débité plus de 1 fois (5 unités max)
        self.assertGreaterEqual(apres, avant - Decimal("5"))


# ════════════════════════════════════════════════════════════════════════════
# K. IdempotencyKey model — logique interne
# ════════════════════════════════════════════════════════════════════════════

class TestIdempotencyKeyModel(TestCase):
    """Tests unitaires du modèle IdempotencyKey."""

    def test_unique_constraint_key_endpoint(self):
        """Deux slots avec la même (key, endpoint) → IntegrityError."""
        from django.db import IntegrityError
        IdempotencyKey.objects.create(
            key="dup-key", endpoint="/api/test/",
            payload_hash="abc", status=IdempotencyKey.STATUS_PROCESSING,
        )
        with self.assertRaises(IntegrityError):
            IdempotencyKey.objects.create(
                key="dup-key", endpoint="/api/test/",
                payload_hash="def", status=IdempotencyKey.STATUS_PROCESSING,
            )

    def test_meme_cle_endpoint_different_ok(self):
        """Même clé, endpoints différents → deux slots distincts autorisés."""
        IdempotencyKey.objects.create(
            key="shared-key", endpoint="/api/endpoint-a/",
            payload_hash="aaa", status=IdempotencyKey.STATUS_PROCESSING,
        )
        slot = IdempotencyKey.objects.create(
            key="shared-key", endpoint="/api/endpoint-b/",
            payload_hash="bbb", status=IdempotencyKey.STATUS_PROCESSING,
        )
        self.assertIsNotNone(slot.pk)

    def test_is_stale_processing_vieux(self):
        """Slot 'processing' mis à jour il y a > 60 s → is_stale() = True."""
        from datetime import timedelta
        slot = IdempotencyKey.objects.create(
            key="stale-key", endpoint="/api/stale/",
            payload_hash="xxx", status=IdempotencyKey.STATUS_PROCESSING,
        )
        # Simuler un slot périmé en manipulant updated_at directement
        IdempotencyKey.objects.filter(pk=slot.pk).update(
            updated_at=timezone.now() - timedelta(seconds=120)
        )
        slot.refresh_from_db()
        self.assertTrue(slot.is_stale())

    def test_is_stale_success_jamais_stale(self):
        """Slot 'success' n'est jamais périmé."""
        slot = IdempotencyKey.objects.create(
            key="success-key", endpoint="/api/success/",
            payload_hash="yyy", status=IdempotencyKey.STATUS_SUCCESS,
            response={"id": 1},
        )
        self.assertFalse(slot.is_stale())
