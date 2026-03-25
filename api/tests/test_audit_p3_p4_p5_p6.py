"""
Tests de vérification P3, P4, P5, P6 — Audit robustesse & cohérence.

P3 : get_caisse_physique_boutique() vs RapportBoutiquesView (multi-boutiques)
P4 : ROLES_AUTORISES pour retrancher_caisse — tous les rôles
P5 : Résilience audit_log() — échec volontaire n'annule pas la transaction métier
P6 : Validations sérialiseurs critiques (collecte, admin_corrections)
"""
import datetime
from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from finance.models import (
    ClientFinance,
    CollecteArgent,
    CaisseSupremeTransaction,
)
from finance.services import get_caisse_physique_boutique, enregistrer_collecte
from inventaire.models import Stock
from produits.models import Produit, Categorie
from ventes.models import Ticket


# ═══════════════════════════════════════════════════════════════════════════════
# P3 — Cohérence multi-boutiques : RapportBoutiquesView vs get_caisse_physique
# ═══════════════════════════════════════════════════════════════════════════════

class TestRapportBoutiquesCoherence(APITestCase):
    """
    Vérifie que caisse_reelle retournée par RapportBoutiquesView est identique
    à get_caisse_physique_boutique(lieu) pour chaque boutique.

    Couvre : cash uniquement, cash + paiements créances, cash - collectes,
             cash - corrections caisse, combinaison complète, multi-boutiques isolées.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntRapport")

        cls.boutique_a = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique A", code="BA",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.boutique_b = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique B", code="BB",
            type_lieu=Lieu.TYPE_MAGASIN,
        )

        # Comptable pour accéder au rapport
        cls.comptable = CustomUser.objects.create_user(
            username="cpt_rapport", password="pass1234",
            role=CustomUser.ROLE_COMPTABLE, entreprise=cls.ent,
        )
        # Admin pour les opérations de service
        cls.admin = CustomUser.objects.create_user(
            username="admin_rapport", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )

        cls.client_fin = ClientFinance.objects.create(
            entreprise=cls.ent, nom="Client Rapport"
        )

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def _ticket_cash(self, lieu, montant):
        n = Ticket.objects.filter(lieu=lieu).count() + 1
        return Ticket.objects.create(
            lieu=lieu,
            date=datetime.date.today(),
            numero=f"T-RAPP-{lieu.code}-{n}",
            montant_total=Decimal(str(montant)),
            montant_cash=Decimal(str(montant)),
        )

    def _collecte(self, lieu, montant_pris):
        return enregistrer_collecte(
            lieu=lieu,
            date_collecte=datetime.date.today(),
            montant_trouve=Decimal(str(montant_pris)),
            montant_pris=Decimal(str(montant_pris)),
            created_by=self.admin,
        )

    def _correction_caisse(self, lieu, montant):
        """Crée un JournalCreance avec retrancher_caisse=True."""
        from finance.services import creer_journal_creance
        creer_journal_creance(
            client=self.client_fin,
            description="Correction test",
            montant_initial=Decimal(str(montant)),
            created_by=self.admin,
            lieu=lieu,
            retrancher_caisse=True,
        )

    def _rapport(self):
        r = self.client.get("/api/comptable/rapport-boutiques/", **self._jwt(self.comptable))
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        return {item["lieu_id"]: item for item in r.json()}

    def test_caisse_zero_boutique_vide(self):
        """Boutique sans ticket → caisse_reelle = 0 = get_caisse_physique."""
        rapport = self._rapport()
        for bid in [self.boutique_a.pk, self.boutique_b.pk]:
            if bid in rapport:
                attendu = str(get_caisse_physique_boutique(
                    self.boutique_a if bid == self.boutique_a.pk else self.boutique_b
                ))
                self.assertEqual(rapport[bid]["caisse_reelle"], attendu)

    def test_cash_seul_concordance(self):
        """Cash ticket boutique A → caisse_reelle = get_caisse_physique."""
        self._ticket_cash(self.boutique_a, 15000)
        rapport = self._rapport()
        attendu = str(get_caisse_physique_boutique(self.boutique_a))
        self.assertEqual(rapport[self.boutique_a.pk]["caisse_reelle"], attendu)

    def test_cash_moins_collecte_concordance(self):
        """Cash 20 000 − collecte 8 000 → caisse_reelle = 12 000 dans le rapport."""
        self._ticket_cash(self.boutique_b, 20000)
        self._collecte(self.boutique_b, 8000)
        rapport = self._rapport()
        attendu = str(get_caisse_physique_boutique(self.boutique_b))
        self.assertEqual(rapport[self.boutique_b.pk]["caisse_reelle"], attendu)
        self.assertEqual(Decimal(rapport[self.boutique_b.pk]["caisse_reelle"]), Decimal("12000"))

    def test_cash_moins_correction_caisse_concordance(self):
        """Cash 25 000 − correction caisse 5 000 → caisse_reelle = 20 000."""
        self._ticket_cash(self.boutique_a, 25000)
        self._correction_caisse(self.boutique_a, 5000)
        rapport = self._rapport()
        attendu = str(get_caisse_physique_boutique(self.boutique_a))
        self.assertEqual(rapport[self.boutique_a.pk]["caisse_reelle"], attendu)
        self.assertEqual(Decimal(rapport[self.boutique_a.pk]["caisse_reelle"]), Decimal("20000"))

    def test_multi_boutiques_isolees(self):
        """Boutique A et B ont des caisses indépendantes — pas de contamination croisée."""
        self._ticket_cash(self.boutique_a, 10000)
        self._ticket_cash(self.boutique_b, 30000)
        self._collecte(self.boutique_b, 10000)

        rapport = self._rapport()

        caisse_a = get_caisse_physique_boutique(self.boutique_a)
        caisse_b = get_caisse_physique_boutique(self.boutique_b)

        self.assertEqual(
            Decimal(rapport[self.boutique_a.pk]["caisse_reelle"]), caisse_a,
            "Boutique A : caisse_reelle doit correspondre à get_caisse_physique_boutique"
        )
        self.assertEqual(
            Decimal(rapport[self.boutique_b.pk]["caisse_reelle"]), caisse_b,
            "Boutique B : caisse_reelle doit correspondre à get_caisse_physique_boutique"
        )
        # Vérification valeurs absolues
        self.assertEqual(caisse_a, Decimal("10000"))
        self.assertEqual(caisse_b, Decimal("20000"))

    def test_combinaison_complete_cash_collecte_correction(self):
        """Cash + collecte + correction → concordance parfaite avec get_caisse_physique."""
        self._ticket_cash(self.boutique_a, 50000)
        self._collecte(self.boutique_a, 15000)
        self._correction_caisse(self.boutique_a, 5000)
        # caisse_physique = 50000 - 15000 - 5000 = 30000

        rapport = self._rapport()
        attendu = get_caisse_physique_boutique(self.boutique_a)
        self.assertEqual(Decimal(rapport[self.boutique_a.pk]["caisse_reelle"]), attendu)
        self.assertEqual(attendu, Decimal("30000"))


# ═══════════════════════════════════════════════════════════════════════════════
# P4 — RBAC retrancher_caisse : tous les rôles
# ═══════════════════════════════════════════════════════════════════════════════

class TestRolesRetracherCaisse(APITestCase):
    """
    Vérifie le RBAC réel sur POST /api/finance/journaux-creances/ avec retrancher_caisse=True.

    Architecture :
      JournalCreanceViewSet utilise DafReadOnlyMixin + IsDafRole.
      → DafReadOnlyMixin bloque DAF et COMPTABLE en écriture (403 "Accès en lecture seule").
      → IsDafRole bloque boutique/usine/collecteur (403 "Réservé au DAF ou aux administrateurs").
      → Le check retrancher_caisse (ROLES_AUTORISES) n'est atteint que par supreme_admin et admin.

    Incohérence identifiée (P4 audit) :
      ROLES_AUTORISES inclut DAF et COMPTABLE mais ils sont bloqués par DafReadOnlyMixin
      avant d'atteindre ce check → le code est dead code pour DAF/COMPTABLE sur cette vue.
      Le service finance.services.solder_journal_payable() a la même liste ROLES_AUTORISES
      mais peut être appelé depuis des voies admin où DAF n'est pas bloqué.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntRBAC")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique RBAC", code="RBAC",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.client_fin = ClientFinance.objects.create(entreprise=cls.ent, nom="Client RBAC")

        # Chaque utilisateur sans lieu assigné (lieu=None) — lieu_id est unique,
        # impossible d'assigner le même lieu à plusieurs users.
        def _u(username, role):
            return CustomUser.objects.create_user(
                username=username, password="pass1234",
                role=role, entreprise=cls.ent,
            )

        cls.supreme = _u("rbac_supreme", CustomUser.ROLE_SUPREME_ADMIN)
        cls.admin = _u("rbac_admin", CustomUser.ROLE_ADMIN)
        cls.daf = _u("rbac_daf", CustomUser.ROLE_DAF)
        cls.comptable = _u("rbac_cpt", CustomUser.ROLE_COMPTABLE)
        cls.boutique_user = _u("rbac_boutique", CustomUser.ROLE_BOUTIQUE)
        cls.usine_user = _u("rbac_usine", CustomUser.ROLE_USINE)
        cls.collecteur_user = _u("rbac_coll", CustomUser.ROLE_COLLECTEUR)

        # Ajouter du cash pour que retrancher_caisse puisse s'exécuter
        Ticket.objects.create(
            lieu=cls.lieu,
            date=datetime.date.today(),
            numero="T-RBAC-CASH",
            montant_total=Decimal("999999"),
            montant_cash=Decimal("999999"),
        )

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def _post(self, user, montant="1000.00", key_suffix=""):
        return self.client.post(
            "/api/finance/journaux-creances/",
            {
                "client_id": self.client_fin.pk,
                "description": "Test RBAC retrancher",
                "montant_initial": montant,
                "retrancher_caisse": True,
                "lieu_id": self.lieu.pk,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"rbac-{user.username}-{key_suffix}",
            **self._jwt(user),
        )

    # ── Rôles vraiment autorisés (atteignent le check retrancher_caisse) ──

    def test_supreme_admin_peut_retrancher(self):
        """ROLE_SUPREME_ADMIN : IsDafRole OK + DafReadOnlyMixin OK (non bloqué) + ROLES_AUTORISES OK."""
        r = self._post(self.supreme, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        self.assertEqual(Decimal(r.json()["correction_caisse"]), Decimal("1000.00"))

    def test_admin_peut_retrancher(self):
        """ROLE_ADMIN : IsDafRole OK + DafReadOnlyMixin OK + ROLES_AUTORISES OK."""
        r = self._post(self.admin, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

    # ── DAF / COMPTABLE : bloqués par DafReadOnlyMixin avant le check ROLES_AUTORISES ──

    def test_daf_bloque_par_read_only_mixin(self):
        """
        DAF est bloqué par DafReadOnlyMixin sur JournalCreanceViewSet (POST = écriture).
        Le check ROLES_AUTORISES n'est pas atteint — code dead pour DAF sur cette vue.
        """
        r = self._post(self.daf, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.json())
        self.assertIn("lecture seule", r.json().get("detail", "").lower())

    def test_comptable_bloque_par_read_only_mixin(self):
        """COMPTABLE : même comportement que DAF — DafReadOnlyMixin bloque avant ROLES_AUTORISES."""
        r = self._post(self.comptable, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.json())
        self.assertIn("lecture seule", r.json().get("detail", "").lower())

    # ── Rôles non autorisés (bloqués par IsDafRole) ──

    def test_boutique_bloque_par_permission(self):
        """ROLE_BOUTIQUE : bloqué par IsDafRole (pas dans le périmètre finance DAF)."""
        r = self._post(self.boutique_user, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.json())
        # IsDafRole retourne "Réservé au DAF ou aux administrateurs."
        self.assertIn("DAF", r.json().get("detail", ""))

    def test_usine_bloque_par_permission(self):
        """ROLE_USINE : bloqué par IsDafRole."""
        r = self._post(self.usine_user, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.json())

    def test_collecteur_bloque_par_permission(self):
        """ROLE_COLLECTEUR : bloqué par IsDafRole."""
        r = self._post(self.collecteur_user, key_suffix="001")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.json())

    def test_admin_sans_cash_bloque_par_service(self):
        """
        Admin avec caisse vide → 400 retourné par la vue (ErreurFinance capturée par _err()).
        Prouve que le check ROLES_AUTORISES est bien atteint pour admin et que le service
        refuse correctement un retrancher_caisse si la caisse est insuffisante.
        """
        from finance.models import JournalCreance, ClientFinance as CF
        ent2 = Entreprise.objects.create(nom="EntCaisseVide2")
        lieu_vide = Lieu.objects.create(
            entreprise=ent2, nom="Boutique Vide", code="BVIDE2",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        admin2 = CustomUser.objects.create_user(
            username="admin_vide2", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=ent2,
        )
        client2 = CF.objects.create(entreprise=ent2, nom="Client Vide2")
        r = self.client.post(
            "/api/finance/journaux-creances/",
            {
                "client_id": client2.pk,
                "description": "Test caisse vide",
                "montant_initial": "1000.00",
                "retrancher_caisse": True,
                "lieu_id": lieu_vide.pk,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbac-admin-caisse-vide-001",
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(admin2).access_token)}",
        )
        # ErreurFinance (caisse insuffisante) → 400 via _err(), pas 403
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())
        self.assertIn("caisse disponible", r.json().get("detail", "").lower())


# ═══════════════════════════════════════════════════════════════════════════════
# P5 — Résilience audit_log : échec volontaire n'annule pas la transaction métier
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogResilience(APITestCase):
    """
    Vérifie le comportement de audit_log() selon son emplacement dans le code.

    Deux patterns coexistent dans KONIS :

    A) DANS @transaction.atomic (ex: finance/services.py) :
       Si audit_log() lève, toute la transaction rollback (comportement attendu).
       Le journal métier N'est PAS créé.

    B) HORS transaction.atomic (ex: api/views/admin_corrections.py) :
       audit_log() est appelé après que l'écriture métier a déjà été committée.
       Si audit_log() lève, l'objet métier reste en DB (500 côté client mais pas de perte de données).
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntAudit")
        cls.admin = CustomUser.objects.create_user(
            username="admin_audit_v2", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique Audit", code="BAP",
            type_lieu=Lieu.TYPE_MAGASIN,
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.admin).access_token)}"}

    # ── Pattern A : audit DANS @transaction.atomic ─────────────────────────────

    def test_pattern_a_audit_dans_transaction_rollback_tout(self):
        """
        Dans finance/services.py, audit_log() est dans @transaction.atomic.
        Un crash audit rollback également le journal payable.
        C'est le comportement ATTENDU pour assurer la cohérence audit ↔ métier.
        """
        from finance.models import JournalPayable, Creancier
        from finance.services import creer_journal_payable

        creancier = Creancier.objects.create(entreprise=self.ent, nom="CreancierAuditA")
        count_avant = JournalPayable.objects.count()

        with patch("finance.services.audit_log", side_effect=Exception("DB audit KO")):
            with self.assertRaises(Exception):
                creer_journal_payable(
                    creancier=creancier,
                    description="Test pattern A",
                    montant_initial=Decimal("5000"),
                    created_by=self.admin,
                )

        # Le journal est rollback car audit est dans la même transaction atomique
        self.assertEqual(
            JournalPayable.objects.count(), count_avant,
            "Pattern A : l'audit dans @transaction.atomic rollback tout si l'audit échoue"
        )

    # ── Pattern B : audit HORS transaction (vues admin_corrections) ────────────

    def test_pattern_b_audit_hors_transaction_objet_persiste(self):
        """
        Dans admin_corrections.py, CaisseSupremeTransaction est créée sans
        transaction.atomic() explicite puis audit_log() est appelé après.
        Si audit_log() lève, l'objet métier est DÉJÀ commis en DB → 500 mais pas de perte.

        raise_request_exception=False est requis car le test client Django re-raise
        les exceptions non catchées par défaut.
        """
        count_avant = CaisseSupremeTransaction.objects.filter(entreprise=self.ent).count()

        # Désactiver la re-raise pour capter le code HTTP sans crash test
        self.client.raise_request_exception = False

        with patch("api.views.admin_corrections.audit_log", side_effect=Exception("DB audit KO")):
            r = self.client.post(
                "/api/admin/corrections/caisse/",
                {
                    "lieu_id": self.boutique.pk,
                    "montant": "1000",
                    "operation": "ajouter",
                    "motif": "Test résilience audit",
                },
                format="json",
                **self._jwt(),
            )

        self.client.raise_request_exception = True  # Restaurer

        # La vue retourne 500 car audit_log() a planté
        self.assertEqual(r.status_code, 500)

        # Mais la CaisseSupremeTransaction est déjà en DB
        self.assertEqual(
            CaisseSupremeTransaction.objects.filter(entreprise=self.ent).count(),
            count_avant + 1,
            "Pattern B : CaisseSupremeTransaction committée avant audit_log() — persiste malgré le crash audit"
        )

    def test_pattern_b_audit_ok_retourne_200(self):
        """Sans crash audit, admin_corrections caisse retourne 200."""
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            {
                "lieu_id": self.boutique.pk,
                "montant": "500",
                "operation": "ajouter",
                "motif": "Test nominal",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, 200, r.json())


# ═══════════════════════════════════════════════════════════════════════════════
# P6 — Validations sérialiseurs critiques
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollecteSerializerValidations(APITestCase):
    """
    Vérifie toutes les validations de CollecteArgentCreateSerializer :
    montant_pris > montant_trouve, valeurs négatives, champs manquants.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntCollecteSer")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique CS", code="BCS",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        # CollecteViewSet.create est réservé exclusivement au rôle COLLECTEUR
        # (vérification dans la vue, pas seulement dans les permissions)
        cls.collecteur = CustomUser.objects.create_user(
            username="coll_cs", password="pass1234",
            role=CustomUser.ROLE_COLLECTEUR, entreprise=cls.ent,
        )
        Ticket.objects.create(
            lieu=cls.lieu,
            date=datetime.date.today(),
            numero="T-CS-001",
            montant_total=Decimal("50000"),
            montant_cash=Decimal("50000"),
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.collecteur).access_token)}"}

    _idem_counter = 0

    def _post(self, payload, key=None):
        TestCollecteSerializerValidations._idem_counter += 1
        headers = self._jwt()
        if key is not False:
            headers["HTTP_IDEMPOTENCY_KEY"] = key or f"collecte-ser-{self._idem_counter}"
        return self.client.post(
            "/api/finance/collectes/",
            payload,
            format="json",
            **headers,
        )

    def test_montant_pris_superieur_montant_trouve_rejete(self):
        """montant_pris > montant_trouve → 400 (validation serializer)."""
        r = self._post({
            "lieu_id": self.lieu.pk,
            "date_collecte": str(datetime.date.today()),
            "montant_trouve": "5000.00",
            "montant_pris": "6000.00",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())
        body = str(r.json())
        self.assertIn("montant_pris", body)

    def test_montant_trouve_egal_montant_pris_accepte(self):
        """montant_pris == montant_trouve → 201."""
        r = self._post({
            "lieu_id": self.lieu.pk,
            "date_collecte": str(datetime.date.today()),
            "montant_trouve": "1000.00",
            "montant_pris": "1000.00",
        })
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())

    def test_montant_negatif_rejete(self):
        """montant_trouve < 0 → 400."""
        r = self._post({
            "lieu_id": self.lieu.pk,
            "date_collecte": str(datetime.date.today()),
            "montant_trouve": "-100.00",
            "montant_pris": "0.00",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())

    def test_montant_pris_negatif_rejete(self):
        """montant_pris < 0 → 400."""
        r = self._post({
            "lieu_id": self.lieu.pk,
            "date_collecte": str(datetime.date.today()),
            "montant_trouve": "5000.00",
            "montant_pris": "-1.00",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())

    def test_lieu_id_manquant_rejete(self):
        """Pas de lieu_id → 400."""
        r = self._post({
            "date_collecte": str(datetime.date.today()),
            "montant_trouve": "5000.00",
            "montant_pris": "1000.00",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())

    def test_date_collecte_manquante_rejetee(self):
        """Pas de date_collecte → 400."""
        r = self._post({
            "lieu_id": self.lieu.pk,
            "montant_trouve": "5000.00",
            "montant_pris": "1000.00",
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.json())

    def test_montant_pris_zero_accepte(self):
        """montant_pris = 0 (collecteur regarde sans prendre) → 201."""
        r = self._post({
            "lieu_id": self.lieu.pk,
            "date_collecte": str(datetime.date.today()),
            "montant_trouve": "5000.00",
            "montant_pris": "0.00",
        })
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())


class TestAdminCorrectionsSerializerValidations(APITestCase):
    """
    Vérifie les validations de AdminCorrectionCaisseSerializer,
    AdminCorrectionStockSerializer et AdminSupprimerTicketSerializer.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntAdminSer")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique AdmSer", code="BAS",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.categorie = Categorie.objects.create(
            nom="Cat AdmSer", entreprise=cls.ent,
        )
        cls.produit = Produit.objects.create(
            nom="Produit AdmSer", code="PAS001", entreprise=cls.ent,
            categorie=cls.categorie,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_adm_ser", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.admin).access_token)}"}

    # ── Correction caisse ──

    def test_caisse_motif_vide_rejete(self):
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            {"lieu_id": self.boutique.pk, "montant": "1000", "operation": "ajouter", "motif": "   "},
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", str(r.json()))

    def test_caisse_montant_zero_rejete(self):
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            {"lieu_id": self.boutique.pk, "montant": "0", "operation": "ajouter", "motif": "Test"},
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("montant", str(r.json()))

    def test_caisse_montant_negatif_rejete(self):
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            {"lieu_id": self.boutique.pk, "montant": "-500", "operation": "ajouter", "motif": "Test"},
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_caisse_lieu_inexistant_rejete(self):
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            {"lieu_id": 99999, "montant": "1000", "operation": "ajouter", "motif": "Test"},
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lieu_id", str(r.json()))

    def test_caisse_operation_invalide_rejetee(self):
        r = self.client.post(
            "/api/admin/corrections/caisse/",
            {"lieu_id": self.boutique.pk, "montant": "1000", "operation": "multiplier", "motif": "Test"},
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Correction stock ──

    def test_stock_quantite_nulle_pour_ajouter_rejetee(self):
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": self.boutique.pk,
                "produit_id": self.produit.pk,
                "operation": "ajouter",
                "motif": "Test",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantite", str(r.json()))

    def test_stock_quantite_negative_rejetee(self):
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": self.boutique.pk,
                "produit_id": self.produit.pk,
                "quantite": "-5",
                "operation": "ajouter",
                "motif": "Test",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stock_supprimer_sans_quantite_accepte(self):
        """L'opération 'supprimer' n'exige pas de quantite."""
        Stock.objects.get_or_create(
            lieu=self.boutique, produit=self.produit,
            defaults={"quantite": Decimal("10")},
        )
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": self.boutique.pk,
                "produit_id": self.produit.pk,
                "operation": "supprimer",
                "motif": "Remise à zéro test",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.json())
        stock = Stock.objects.get(lieu=self.boutique, produit=self.produit)
        self.assertEqual(stock.quantite, Decimal("0"))

    def test_stock_motif_vide_rejete(self):
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": self.boutique.pk,
                "produit_id": self.produit.pk,
                "quantite": "5",
                "operation": "ajouter",
                "motif": "",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", str(r.json()))

    def test_stock_produit_inexistant_rejete(self):
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": self.boutique.pk,
                "produit_id": 99999,
                "quantite": "5",
                "operation": "ajouter",
                "motif": "Test",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("produit_id", str(r.json()))

    def test_stock_retrancher_plus_que_stock_rejete(self):
        """Retrancher plus que le stock disponible → 400."""
        Stock.objects.filter(lieu=self.boutique, produit=self.produit).delete()
        Stock.objects.create(
            lieu=self.boutique, produit=self.produit, quantite=Decimal("3"),
        )
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": self.boutique.pk,
                "produit_id": self.produit.pk,
                "quantite": "10",
                "operation": "retrancher",
                "motif": "Test retrancher",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stock_cross_tenant_lieu_rejete(self):
        """Lieu appartenant à une autre entreprise → 400."""
        ent2 = Entreprise.objects.create(nom="EntCrossTenant")
        lieu2 = Lieu.objects.create(
            entreprise=ent2, nom="Boutique AutreEnt", code="BAUTRE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        r = self.client.post(
            "/api/admin/corrections/stock/",
            {
                "lieu_id": lieu2.pk,
                "produit_id": self.produit.pk,
                "quantite": "5",
                "operation": "ajouter",
                "motif": "Cross-tenant test",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lieu_id", str(r.json()))
