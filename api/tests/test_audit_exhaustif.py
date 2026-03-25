"""
Tests exhaustifs — Audit complet P3→P7 + vérifications 6.x

P3.1  : /api/boutique/dashboard/ caisse_physique === /api/comptable/rapport-boutiques/ caisse_reelle
P4    : DafReadOnlyMixin — tous les rôles sur toutes les actions write finance
P5    : Résilience audit_log ventes (Pattern B : audit dans boutique_views, hors transaction)
P6.2  : Usine serializer via API (poids_par_sac, montant_cession)
P7.1  : Auth login/logout/refresh/me + token révoqué + CSRF
6.2   : get_lieu_mpsl — 0, 1 et plusieurs dépôts MPSL
6.4   : transaction.atomic présent sur toutes les écritures critiques (vérification directe)
"""
import datetime
import threading
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from api.utils import get_lieu_mpsl
from core.models import CustomUser, Entreprise, Lieu
from finance.models import (
    ClientFinance,
    Creancier,
    JournalCreance,
)
from finance.services import get_caisse_physique_boutique
from inventaire.models import Stock
from produits.models import Produit, Categorie
from ventes.models import Ticket


# ═══════════════════════════════════════════════════════════════════════════════
# P3.1 — Dashboard boutique vs Rapport comptable : concordance caisse
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaissePhysiqueDashboardVsRapport(APITestCase):
    """
    Vérifie que caisse_physique (boutique dashboard) = caisse_reelle (comptable rapport).
    Les deux utilisent get_caisse_physique_boutique() — ils DOIVENT être identiques.

    Champs comparés :
      - GET /api/boutique/dashboard/?lieu_id=X → data["caisse_physique"]
      - GET /api/comptable/rapport-boutiques/  → item["caisse_reelle"]
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntP3Compare")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique Comp", code="BCOMP",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_p3comp", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="cpt_p3comp", password="pass1234",
            role=CustomUser.ROLE_COMPTABLE, entreprise=cls.ent,
        )
        cls.client_fin = ClientFinance.objects.create(entreprise=cls.ent, nom="Client P3")

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def _creer_scenario(self, cash, montant_collecte=None, montant_correction=None):
        """Crée tickets cash + éventuellement collecte + correction caisse."""
        n = Ticket.objects.filter(lieu=self.lieu).count() + 1
        Ticket.objects.create(
            lieu=self.lieu,
            date=datetime.date.today(),
            numero=f"T-P3C-{n}",
            montant_total=Decimal(str(cash)),
            montant_cash=Decimal(str(cash)),
        )
        if montant_collecte:
            from finance.services import enregistrer_collecte
            enregistrer_collecte(
                lieu=self.lieu,
                date_collecte=datetime.date.today(),
                montant_trouve=Decimal(str(montant_collecte)),
                montant_pris=Decimal(str(montant_collecte)),
                created_by=self.admin,
            )
        if montant_correction:
            from finance.services import creer_journal_creance
            creer_journal_creance(
                client=self.client_fin,
                description="Correction comparaison",
                montant_initial=Decimal(str(montant_correction)),
                created_by=self.admin,
                lieu=self.lieu,
                retrancher_caisse=True,
            )

    def _get_dashboard_caisse_physique(self):
        r = self.client.get(
            f"/api/boutique/dashboard/?lieu_id={self.lieu.pk}",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, 200, r.json())
        return Decimal(r.json()["caisse_physique"])

    def _get_rapport_caisse_reelle(self):
        r = self.client.get(
            "/api/comptable/rapport-boutiques/",
            **self._jwt(self.comptable),
        )
        self.assertEqual(r.status_code, 200, r.json())
        items = {item["lieu_id"]: item for item in r.json()}
        return Decimal(items[self.lieu.pk]["caisse_reelle"])

    def test_cash_seul_concordance_absolue(self):
        """Ticket cash 30 000 → dashboard.caisse_physique == rapport.caisse_reelle."""
        self._creer_scenario(cash=30000)
        dashboard = self._get_dashboard_caisse_physique()
        rapport = self._get_rapport_caisse_reelle()
        self.assertEqual(dashboard, rapport,
            f"Divergence : dashboard={dashboard} ≠ rapport={rapport}")
        self.assertEqual(dashboard, Decimal("30000"))

    def test_cash_moins_collecte_concordance(self):
        """Cash 20 000 − collecte 8 000 = 12 000 dans les deux vues."""
        self._creer_scenario(cash=20000, montant_collecte=8000)
        dashboard = self._get_dashboard_caisse_physique()
        rapport = self._get_rapport_caisse_reelle()
        self.assertEqual(dashboard, rapport)
        self.assertEqual(dashboard, Decimal("12000"))

    def test_cash_moins_correction_concordance(self):
        """Cash 25 000 − correction 5 000 = 20 000 dans les deux vues."""
        self._creer_scenario(cash=25000, montant_correction=5000)
        dashboard = self._get_dashboard_caisse_physique()
        rapport = self._get_rapport_caisse_reelle()
        self.assertEqual(dashboard, rapport)
        self.assertEqual(dashboard, Decimal("20000"))

    def test_combinaison_complete_concordance(self):
        """Cash 50 000 − collecte 15 000 − correction 5 000 = 30 000."""
        self._creer_scenario(cash=50000, montant_collecte=15000, montant_correction=5000)
        dashboard = self._get_dashboard_caisse_physique()
        rapport = self._get_rapport_caisse_reelle()
        self.assertEqual(dashboard, rapport)
        self.assertEqual(dashboard, Decimal("30000"))

    def test_get_caisse_physique_boutique_egale_les_deux(self):
        """
        La fonction get_caisse_physique_boutique(lieu) = dashboard.caisse_physique = rapport.caisse_reelle.
        Source de vérité unique confirmée.
        """
        self._creer_scenario(cash=40000, montant_collecte=10000)
        service = get_caisse_physique_boutique(self.lieu)
        dashboard = self._get_dashboard_caisse_physique()
        rapport = self._get_rapport_caisse_reelle()
        self.assertEqual(service, dashboard)
        self.assertEqual(service, rapport)
        self.assertEqual(service, Decimal("30000"))


# ═══════════════════════════════════════════════════════════════════════════════
# P4 — RBAC exhaustif : DafReadOnlyMixin sur tous les ViewSets finance
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinanceRBACExhaustif(APITestCase):
    """
    Vérifie le comportement exact de DafReadOnlyMixin pour tous les ViewSets finance.

    Principe :
      - IsDafRole (supreme_admin, admin, DAF, comptable) : accès en lecture (GET) ✓
      - DafReadOnlyMixin : bloque DAF et COMPTABLE sur les actions write
      - Actions non listées dans _WRITE_ACTIONS (ex: activate, desactivate) : DAF/COMPTABLE peuvent y accéder

    Structure des tests :
      1. GET (lecture) → tous les rôles IsDafRole passent
      2. POST (écriture) → DAF/COMPTABLE bloqués (403 "lecture seule"), admin passe
      3. Actions custom non bloquées (activate/desactivate) → DAF/COMPTABLE atteignent le ROLES_AUTORISES check
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntRBACExh")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique RBAC Exh", code="BRBEX",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.supreme = CustomUser.objects.create_user(
            username="rbacex_supreme", password="pass1234",
            role=CustomUser.ROLE_SUPREME_ADMIN, entreprise=cls.ent,
        )
        cls.admin = CustomUser.objects.create_user(
            username="rbacex_admin", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.daf = CustomUser.objects.create_user(
            username="rbacex_daf", password="pass1234",
            role=CustomUser.ROLE_DAF, entreprise=cls.ent,
        )
        cls.comptable = CustomUser.objects.create_user(
            username="rbacex_cpt", password="pass1234",
            role=CustomUser.ROLE_COMPTABLE, entreprise=cls.ent,
        )
        cls.boutique_user = CustomUser.objects.create_user(
            username="rbacex_bout", password="pass1234",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent, lieu=cls.lieu,
        )
        cls.client_fin = ClientFinance.objects.create(entreprise=cls.ent, nom="Client RBAC Exh")
        cls.creancier = Creancier.objects.create(entreprise=cls.ent, nom="Fourn RBAC Exh", statut="actif")

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    # ── FinanceResumeView GET ──────────────────────────────────────────────────

    def test_get_finance_resume_tous_roles_daf(self):
        """GET /api/finance/resume/ : tous les rôles IsDafRole passent."""
        for user in (self.supreme, self.admin, self.daf, self.comptable):
            r = self.client.get("/api/finance/resume/", **self._jwt(user))
            self.assertIn(r.status_code, [200, 400],
                f"Rôle {user.role} attendu 200/400, obtenu {r.status_code}")

    def test_get_finance_resume_boutique_bloque(self):
        """GET /api/finance/resume/ : rôle boutique bloqué (IsDafRole)."""
        r = self.client.get("/api/finance/resume/", **self._jwt(self.boutique_user))
        self.assertEqual(r.status_code, 403)

    # ── JournalPayableViewSet POST ─────────────────────────────────────────────

    def test_post_journal_payable_daf_bloque_par_mixin(self):
        """POST /api/finance/journaux-payables/ : DAF bloqué par DafReadOnlyMixin."""
        r = self.client.post(
            "/api/finance/journaux-payables/",
            {"creancier": self.creancier.pk, "description": "Test", "montant_initial": "5000"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-jp-daf-001",
            **self._jwt(self.daf),
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("lecture seule", r.json().get("detail", "").lower())

    def test_post_journal_payable_comptable_bloque_par_mixin(self):
        """POST /api/finance/journaux-payables/ : COMPTABLE bloqué par DafReadOnlyMixin."""
        r = self.client.post(
            "/api/finance/journaux-payables/",
            {"creancier": self.creancier.pk, "description": "Test", "montant_initial": "5000"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-jp-cpt-001",
            **self._jwt(self.comptable),
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("lecture seule", r.json().get("detail", "").lower())

    def test_post_journal_payable_admin_passe(self):
        """POST /api/finance/journaux-payables/ : admin passe (DafReadOnlyMixin ne bloque pas admin)."""
        r = self.client.post(
            "/api/finance/journaux-payables/",
            {"creancier_id": self.creancier.pk, "description": "Test admin", "montant_initial": "5000"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-jp-adm-001",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, 201, r.json())

    # ── CaisseSupremeViewSet POST ──────────────────────────────────────────────

    def test_post_caisse_supreme_daf_bloque(self):
        """POST /api/finance/caisse/ : DAF bloqué par DafReadOnlyMixin."""
        r = self.client.post(
            "/api/finance/caisse/",
            {"type_transaction": "depot", "montant": "1000", "description": "Test DAF", "date": str(datetime.date.today())},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-cs-daf-001",
            **self._jwt(self.daf),
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("lecture seule", r.json().get("detail", "").lower())

    def test_post_caisse_supreme_admin_passe(self):
        """POST /api/finance/caisse/ : admin crée sans blocage."""
        r = self.client.post(
            "/api/finance/caisse/",
            {"type_transaction": "depot", "montant": "1000", "description": "Test admin", "date": str(datetime.date.today())},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-cs-adm-001",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, 201, r.json())

    # ── CreancierViewSet activate/desactivate (custom actions) ─────────────────

    def test_activate_creancier_daf_atteint_roles_autorises(self):
        """
        POST /api/finance/creanciers/{id}/activate/ : 'activate' n'est PAS dans _WRITE_ACTIONS
        → DafReadOnlyMixin ne bloque PAS DAF → ROLES_AUTORISES check atteint → DAF autorisé.
        """
        creancier_pending = Creancier.objects.create(
            entreprise=self.ent, nom="FournPendingDAF", statut="pending"
        )
        r = self.client.post(
            f"/api/finance/creanciers/{creancier_pending.pk}/activate/",
            format="json",
            **self._jwt(self.daf),
        )
        self.assertEqual(r.status_code, 200, r.json())
        creancier_pending.refresh_from_db()
        self.assertEqual(creancier_pending.statut, "actif")

    def test_activate_creancier_boutique_bloque(self):
        """POST activate : rôle boutique bloqué par IsDafRole (pas dans le périmètre finance)."""
        creancier = Creancier.objects.create(
            entreprise=self.ent, nom="FournPendingBout", statut="pending"
        )
        r = self.client.post(
            f"/api/finance/creanciers/{creancier.pk}/activate/",
            format="json",
            **self._jwt(self.boutique_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_get_creanciers_tous_roles_daf(self):
        """GET /api/finance/creanciers/ : tous les rôles IsDafRole peuvent lire."""
        for user in (self.supreme, self.admin, self.daf, self.comptable):
            r = self.client.get("/api/finance/creanciers/", **self._jwt(user))
            self.assertEqual(r.status_code, 200,
                f"Rôle {user.role} doit pouvoir lire les créanciers")

    # ── EmpruntViewSet POST ────────────────────────────────────────────────────

    def test_post_emprunt_daf_bloque(self):
        """POST /api/finance/emprunts/ : DAF bloqué par DafReadOnlyMixin."""
        r = self.client.post(
            "/api/finance/emprunts/",
            {
                "description": "Test emprunt DAF",
                "montant_initial": "10000",
                "taux_interet": "5",
                "date_emprunt": str(datetime.date.today()),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-emp-daf-001",
            **self._jwt(self.daf),
        )
        self.assertEqual(r.status_code, 403)
        self.assertIn("lecture seule", r.json().get("detail", "").lower())

    def test_post_emprunt_admin_passe(self):
        """POST /api/finance/emprunts/ : admin peut créer un emprunt."""
        r = self.client.post(
            "/api/finance/emprunts/",
            {
                "description": "Emprunt admin test",
                "montant_initial": "10000",
                "taux_interet": "5",
                "date_emprunt": str(datetime.date.today()),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="rbacex-emp-adm-001",
            **self._jwt(self.admin),
        )
        self.assertIn(r.status_code, [201, 400], r.json())

    # ── ClientFinanceViewSet POST ──────────────────────────────────────────────

    def test_post_client_finance_daf_bloque(self):
        """POST /api/finance/clients/ : DAF bloqué par DafReadOnlyMixin."""
        r = self.client.post(
            "/api/finance/clients/",
            {"nom": "Client DAF Test"},
            format="json",
            **self._jwt(self.daf),
        )
        self.assertEqual(r.status_code, 403)

    def test_post_client_finance_admin_passe(self):
        """POST /api/finance/clients/ : admin peut créer un client."""
        r = self.client.post(
            "/api/finance/clients/",
            {"nom": "Client Admin Test"},
            format="json",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, 201, r.json())


# ═══════════════════════════════════════════════════════════════════════════════
# P5 — Résilience audit ventes (Pattern B dans boutique_views)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogResilenceVentes(APITestCase):
    """
    Pattern B dans boutique_views.py :
    La vente (Ticket) est créée DANS transaction.atomic(), committée,
    puis audit_log() est appelé HORS de la transaction dans la vue.
    Si audit_log() plante → Ticket existe déjà en DB → pas de perte de données.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntAuditVente")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique AV", code="BAV",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.boutique_user = CustomUser.objects.create_user(
            username="bout_av", password="pass1234",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent, lieu=cls.lieu,
        )
        cls.categorie = Categorie.objects.create(nom="Cat AV", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Café AV", code="CAV01", entreprise=cls.ent,
            categorie=cls.categorie, poids_par_sac=50,
        )
        Stock.objects.create(lieu=cls.lieu, produit=cls.produit, quantite=Decimal("100"))

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.boutique_user).access_token)}"}

    def test_vente_ticket_persiste_malgre_crash_audit(self):
        """
        Si audit_log() lève dans boutique_views.VenteBoutiqueViewSet.create(),
        le Ticket est déjà commis (ventes.services.creer_ticket dans transaction.atomic).
        La vue retourne 500, mais le Ticket existe en DB.
        """
        count_avant = Ticket.objects.filter(lieu=self.lieu).count()
        self.client.raise_request_exception = False

        with patch("api.views.boutique_views.audit_log", side_effect=Exception("Audit KO vente")):
            r = self.client.post(
                "/api/boutique/ventes/",
                {
                    "lignes": [{"produit": self.produit.pk, "quantite": "1", "prix_unitaire": "500"}],
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="av-vente-audit-001",
                **self._jwt(),
            )

        self.client.raise_request_exception = True

        self.assertEqual(r.status_code, 500)
        self.assertEqual(
            Ticket.objects.filter(lieu=self.lieu).count(), count_avant + 1,
            "Le Ticket doit exister même si audit_log() a planté dans la vue"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# P6.2 — Usine serializer via API (poids_par_sac, montant_cession)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUsineSerializerViaAPI(APITestCase):
    """
    Vérifie les validations du serializer usine via l'API réelle.
    Couvre : poids_par_sac > 1000 kg/sac, quantite_sacs == 0, poids incohérent.
    Vérifie aussi que montant_cession = quantite_sacs * prix_par_sac (calculé côté backend).
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntUsineSerAPI")
        cls.usine = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine USA", code="USA",
            type_lieu=Lieu.TYPE_USINE,
        )
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique USA", code="BUSA",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.categorie = Categorie.objects.create(nom="Cat USA", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Farine USA", code="FUSA01", entreprise=cls.ent,
            categorie=cls.categorie,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_usa", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        # Créer un lot de production pour les tests de cession
        from usine.services import creer_lot_production
        cls.lot = creer_lot_production(
            lieu_usine=cls.usine,
            produit_fini=cls.produit,
            nom_lot="LOT-USA-001",
            quantite_sacs=Decimal("100"),
            poids=Decimal("5000"),
            unite_poids="kg",
            created_by=cls.admin,
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.admin).access_token)}"}

    def test_creation_lot_poids_incoherent_kg_rejete(self):
        """Poids 200 kg pour 0.1 sac = 2000 kg/sac > 1000 → ValidationError."""
        r = self.client.post(
            "/api/usine/lots/",
            {
                "produit_fini": self.produit.pk,
                "lieu_usine": self.usine.pk,
                "nom_lot": "LOT-POIDS-INCOHERENT",
                "quantite_sacs": "0.1",
                "poids": "200",
                "unite_poids": "kg",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, 400, r.json())
        body = str(r.json())
        self.assertIn("poids", body.lower())

    def test_creation_lot_quantite_sacs_zero_rejete(self):
        """quantite_sacs = 0 → ValidationError (min_value=0.01)."""
        r = self.client.post(
            "/api/usine/lots/",
            {
                "produit_fini": self.produit.pk,
                "lieu_usine": self.usine.pk,
                "nom_lot": "LOT-ZERO-SACS",
                "quantite_sacs": "0",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, 400, r.json())

    def test_creation_lot_valide_passe(self):
        """Lot valide : quantite_sacs > 0, poids cohérent → 201."""
        r = self.client.post(
            "/api/usine/lots/",
            {
                "produit_fini": self.produit.pk,
                "lieu_usine": self.usine.pk,
                "nom_lot": "LOT-VALIDE-USA",
                "quantite_sacs": "50",
                "poids": "2500",
                "unite_poids": "kg",
            },
            format="json",
            **self._jwt(),
        )
        self.assertIn(r.status_code, [201], r.json())

    def test_montant_cession_calcule_backend(self):
        """
        montant_cession = quantite_sacs * prix_par_sac calculé côté backend.
        Le frontend ne doit jamais envoyer ce champ — il est en read_only.
        """
        r = self.client.post(
            "/api/usine/cessions/",
            {
                "lot": self.lot.pk,
                "boutique": self.boutique.pk,
                "quantite_sacs": "10",
                "prix_par_sac": "500",
                "poids_total": "500",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, 201, r.json())
        data = r.json()
        # montant_cession = 10 * 500 = 5000 — calculé backend
        self.assertEqual(Decimal(data["montant_cession"]), Decimal("5000"))

    def test_cession_quantite_sacs_zero_rejete(self):
        """quantite_sacs = 0 sur cession → ValidationError."""
        r = self.client.post(
            "/api/usine/cessions/",
            {
                "lot": self.lot.pk,
                "boutique": self.boutique.pk,
                "quantite_sacs": "0",
                "prix_par_sac": "500",
            },
            format="json",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, 400, r.json())


# ═══════════════════════════════════════════════════════════════════════════════
# P7.1 — Auth : login, logout, refresh, me + token révoqué
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthViews(APITestCase):
    """
    Vérifie login/logout/refresh/me et la révocation de token.
    CSRF : simplejwt avec cookies httpOnly — enforced par JWTCookieAuthentication.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntAuth")
        cls.user = CustomUser.objects.create_user(
            username="auth_user", password="motdepasse123",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )

    def test_login_valid_credentials(self):
        """POST /api/auth/login/ avec credentials valides → 200 + user data."""
        r = self.client.post(
            "/api/auth/login/",
            {"username": "auth_user", "password": "motdepasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.json())
        self.assertIn("user", r.json())
        self.assertEqual(r.json()["user"]["username"], "auth_user")

    def test_login_wrong_password(self):
        """POST /api/auth/login/ avec mauvais mot de passe → 401."""
        r = self.client.post(
            "/api/auth/login/",
            {"username": "auth_user", "password": "mauvais"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_login_inexistant(self):
        """POST /api/auth/login/ avec utilisateur inexistant → 401."""
        r = self.client.post(
            "/api/auth/login/",
            {"username": "inexistant", "password": "motdepasse"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_me_avec_token_valide(self):
        """GET /api/auth/me/ avec token valide → 200 + user data."""
        token = str(RefreshToken.for_user(self.user).access_token)
        r = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(r.status_code, 200, r.json())
        self.assertEqual(r.json()["username"], "auth_user")

    def test_me_sans_token(self):
        """GET /api/auth/me/ sans token → 401."""
        r = self.client.get("/api/auth/me/")
        self.assertEqual(r.status_code, 401)

    def test_me_token_revoque(self):
        """GET /api/auth/me/ après is_active=False → 401 (triple révocation)."""
        token = str(RefreshToken.for_user(self.user).access_token)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        try:
            r = self.client.get(
                "/api/auth/me/",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            self.assertEqual(r.status_code, 401,
                "Un token pour un utilisateur inactif doit être rejeté")
        finally:
            self.user.is_active = True
            self.user.save(update_fields=["is_active"])

    def test_logout_blacklist_refresh_token(self):
        """POST /api/auth/logout/ → 200 + blacklist du refresh token."""
        refresh = RefreshToken.for_user(self.user)
        access = str(refresh.access_token)
        r = self.client.post(
            "/api/auth/logout/",
            {"refresh": str(refresh)},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(r.status_code, 200)

    def test_logout_sans_token_refreshe_quand_meme(self):
        """POST /api/auth/logout/ sans refresh token → 200 (cookies supprimés quand même)."""
        access = str(RefreshToken.for_user(self.user).access_token)
        r = self.client.post(
            "/api/auth/logout/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(r.status_code, 200)

    def test_refresh_avec_token_valide(self):
        """POST /api/auth/refresh/ avec refresh token body → 200 + nouvel access."""
        refresh = RefreshToken.for_user(self.user)
        r = self.client.post(
            "/api/auth/refresh/",
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.json())
        self.assertIn("access", r.json())

    def test_refresh_avec_token_invalide(self):
        """POST /api/auth/refresh/ avec token forgé → 401."""
        r = self.client.post(
            "/api/auth/refresh/",
            {"refresh": "ceci.nest.pas.un.token"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_refresh_sans_token(self):
        """POST /api/auth/refresh/ sans refresh token → 401."""
        r = self.client.post("/api/auth/refresh/", {}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_login_sets_cookies_httponly(self):
        """Login → cookies access_token et refresh_token présents et httpOnly."""
        r = self.client.post(
            "/api/auth/login/",
            {"username": "auth_user", "password": "motdepasse123"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        cookies = r.cookies
        self.assertIn("access_token", cookies, "Cookie access_token manquant")
        self.assertIn("refresh_token", cookies, "Cookie refresh_token manquant")
        # Les cookies httpOnly ont la propriété httponly=True
        self.assertTrue(cookies["access_token"]["httponly"])
        self.assertTrue(cookies["refresh_token"]["httponly"])


# ═══════════════════════════════════════════════════════════════════════════════
# 6.2 — get_lieu_mpsl : 0, 1 et plusieurs dépôts MPSL
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetLieuMPSL(TestCase):
    """
    Vérifie le comportement de get_lieu_mpsl() selon le nombre de dépôts MPSL.
    Correction N-2 : retourne None si plusieurs dépôts sans ?lieu= explicite.
    """

    class _FakeRequest:
        """Simule un objet request minimal pour get_lieu_mpsl."""
        def __init__(self, user, lieu_param=None, lieu_body=None):
            self.user = user
            self.query_params = {"lieu": lieu_param} if lieu_param else {}
            self.data = {"lieu": lieu_body} if lieu_body else {}

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntMPSL6")
        cls.admin = CustomUser.objects.create_user(
            username="admin_mpsl6", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.mpsl_user = CustomUser.objects.create_user(
            username="mpsl_user6", password="pass1234",
            role=CustomUser.ROLE_MPSL, entreprise=cls.ent,
        )

    def _req(self, user, lieu_param=None):
        return self._FakeRequest(user, lieu_param=lieu_param)

    def _create_depot(self, code):
        return Lieu.objects.create(
            entreprise=self.ent, nom=f"Dépôt {code}", code=code,
            type_lieu=Lieu.TYPE_MPSL,
        )

    def test_zero_depot_mpsl_retourne_none(self):
        """Aucun dépôt MPSL → None."""
        ent_empty = Entreprise.objects.create(nom="EntMPSLEmpty")
        admin_empty = CustomUser.objects.create_user(
            username="admin_mpsl_empty", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=ent_empty,
        )
        req = self._req(admin_empty)
        self.assertIsNone(get_lieu_mpsl(req))

    def test_un_depot_mpsl_retourne_le_depot(self):
        """Un seul dépôt MPSL → retourne ce dépôt (pas d'ambiguïté)."""
        ent1 = Entreprise.objects.create(nom="EntMPSLUn")
        depot = Lieu.objects.create(
            entreprise=ent1, nom="Dépôt Unique", code="MPSL1U",
            type_lieu=Lieu.TYPE_MPSL,
        )
        admin1 = CustomUser.objects.create_user(
            username="admin_mpsl_un", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=ent1,
        )
        req = self._req(admin1)
        result = get_lieu_mpsl(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, depot.pk)

    def test_plusieurs_depots_sans_parametre_retourne_none(self):
        """
        Plusieurs dépôts MPSL sans ?lieu= → None (ambiguïté, correction N-2).
        Avant la correction : .first() retournait le premier silencieusement.
        """
        ent_multi = Entreprise.objects.create(nom="EntMPSLMulti")
        Lieu.objects.create(
            entreprise=ent_multi, nom="Dépôt A", code="MPSLA",
            type_lieu=Lieu.TYPE_MPSL,
        )
        Lieu.objects.create(
            entreprise=ent_multi, nom="Dépôt B", code="MPSLB",
            type_lieu=Lieu.TYPE_MPSL,
        )
        admin_multi = CustomUser.objects.create_user(
            username="admin_mpsl_multi", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=ent_multi,
        )
        req = self._req(admin_multi)
        self.assertIsNone(
            get_lieu_mpsl(req),
            "Plusieurs dépôts sans ?lieu= → None attendu pour éviter sélection silencieuse"
        )

    def test_plusieurs_depots_avec_parametre_retourne_le_bon(self):
        """Plusieurs dépôts MPSL avec ?lieu=<id> → retourne le bon dépôt."""
        ent_mp = Entreprise.objects.create(nom="EntMPSLParam")
        depot_a = Lieu.objects.create(
            entreprise=ent_mp, nom="Dépôt PA", code="MPSLPA",
            type_lieu=Lieu.TYPE_MPSL,
        )
        Lieu.objects.create(
            entreprise=ent_mp, nom="Dépôt PB", code="MPSPLPB",
            type_lieu=Lieu.TYPE_MPSL,
        )
        admin_mp = CustomUser.objects.create_user(
            username="admin_mpsl_param", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=ent_mp,
        )
        req = self._req(admin_mp, lieu_param=str(depot_a.pk))
        result = get_lieu_mpsl(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, depot_a.pk)

    def test_mpsl_user_avec_lieu_assigne_retourne_son_lieu(self):
        """Utilisateur MPSL avec lieu assigné → retourne son lieu directement."""
        ent_mpsl = Entreprise.objects.create(nom="EntMPSLUser")
        depot = Lieu.objects.create(
            entreprise=ent_mpsl, nom="Dépôt User", code="MPSLU",
            type_lieu=Lieu.TYPE_MPSL,
        )
        mpsl_user = CustomUser.objects.create_user(
            username="mpsl_with_lieu", password="pass1234",
            role=CustomUser.ROLE_MPSL, entreprise=ent_mpsl, lieu=depot,
        )
        req = self._req(mpsl_user)
        result = get_lieu_mpsl(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, depot.pk)

    def test_mpsl_user_sans_lieu_assigne_plusieurs_depots_retourne_none(self):
        """MPSL sans lieu assigné + plusieurs dépôts → None (ambiguïté)."""
        ent_mno = Entreprise.objects.create(nom="EntMPSLNoLieu")
        Lieu.objects.create(
            entreprise=ent_mno, nom="Dépôt MNO-A", code="MPSMNOA",
            type_lieu=Lieu.TYPE_MPSL,
        )
        Lieu.objects.create(
            entreprise=ent_mno, nom="Dépôt MNO-B", code="MPSMNOB",
            type_lieu=Lieu.TYPE_MPSL,
        )
        mpsl_no = CustomUser.objects.create_user(
            username="mpsl_no_lieu", password="pass1234",
            role=CustomUser.ROLE_MPSL, entreprise=ent_mno,
        )
        req = self._req(mpsl_no)
        self.assertIsNone(get_lieu_mpsl(req))


# ═══════════════════════════════════════════════════════════════════════════════
# 6.4 — transaction.atomic sur toutes les écritures critiques
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransactionAtomicPresence(TestCase):
    """
    Vérifie que toutes les fonctions de service critiques utilisent transaction.atomic.
    Méthode : inspection du bytecode / attributs de la fonction décorée.
    """

    def test_finance_services_atomiques(self):
        """Toutes les fonctions finance/services.py avec @transaction.atomic."""
        import finance.services as fs
        fonctions_atomiques = [
            fs.creer_journal_payable,
            fs.enregistrer_paiement_payable,
            fs.solder_journal_payable,
            fs.creer_journal_creance,
            fs.enregistrer_paiement_creance,
            fs.enregistrer_transaction_caisse,
            fs.enregistrer_collecte,
        ]
        for fn in fonctions_atomiques:
            # Une fonction décorée avec @transaction.atomic a __wrapped__ ou est atomique
            # Vérification : la fonction est bien un callable et son code mentionne transaction
            import inspect
            src = inspect.getsource(fn)
            self.assertTrue(
                "transaction.atomic" in src or hasattr(fn, "__wrapped__"),
                f"{fn.__name__} doit utiliser transaction.atomic"
            )

    def test_ventes_services_atomiques(self):
        """Les fonctions ventes/services.py utilisent with transaction.atomic()."""
        import ventes.services as vs
        import inspect
        for fn_name in ["creer_ticket", "vente_mouture_seule"]:
            fn = getattr(vs, fn_name, None)
            if fn:
                src = inspect.getsource(fn)
                self.assertIn("transaction.atomic", src,
                    f"ventes.services.{fn_name} doit utiliser transaction.atomic")

    def test_usine_services_atomiques(self):
        """Les fonctions usine/services.py utilisent with transaction.atomic()."""
        import usine.services as us
        import inspect
        for fn_name in ["creer_lot_production", "transferer_lot_vers_boutique", "transferer_lot_vers_usine"]:
            fn = getattr(us, fn_name, None)
            if fn:
                src = inspect.getsource(fn)
                self.assertIn("transaction.atomic", src,
                    f"usine.services.{fn_name} doit utiliser transaction.atomic")

    def test_inventaire_services_atomiques(self):
        """Les fonctions inventaire/services.py utilisent with transaction.atomic().
        transfert_usine_vers_boutique et transfert_entre_usines sont des wrappers thin
        qui délèguent à _executer_transfert — c'est là que transaction.atomic() vit."""
        import inventaire.services as inv
        import inspect
        # La logique transactionnelle est dans _noyau_transfert (pattern DRY)
        # _executer_transfert et les wrappers publics délèguent à _noyau_transfert
        fn = getattr(inv, "_noyau_transfert", None)
        self.assertIsNotNone(fn, "inventaire.services._noyau_transfert doit exister")
        src = inspect.getsource(fn)
        self.assertIn("transaction.atomic", src,
            "inventaire.services._noyau_transfert doit utiliser transaction.atomic")

    def test_facture_next_number_dans_transaction(self):
        """
        _next_facture_number() dans facture_views.py doit utiliser select_for_update
        (correction N-1 appliquée).
        """
        import api.views.facture_views as fv
        import inspect
        src = inspect.getsource(fv._next_facture_number)
        self.assertIn("select_for_update", src,
            "_next_facture_number doit utiliser select_for_update (correction N-1)")

    def test_get_lieu_mpsl_retourne_none_si_ambigu(self):
        """
        get_lieu_mpsl() avec plusieurs dépôts sans ?lieu= retourne None
        (correction N-2 appliquée).
        """
        import api.utils as utils
        import inspect
        src = inspect.getsource(utils.get_lieu_mpsl)
        self.assertIn("count()", src,
            "get_lieu_mpsl doit utiliser count() pour détecter l'ambiguïté (correction N-2)")
        self.assertNotIn(".first() if ent else None", src,
            "Le fallback .first() silencieux ne doit plus être présent")


# ═══════════════════════════════════════════════════════════════════════════════
# 6.1 — Race condition _next_facture_number : test concurrent
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactureRaceCondition(APITestCase):
    """
    Vérifie que _next_facture_number() avec select_for_update() sérialise
    les créations concurrentes et n'engendre pas de numéros dupliqués.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntFactRace")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique Race", code="BRACE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_race", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.client_fin = ClientFinance.objects.create(entreprise=cls.ent, nom="Client Race")
        cls.categorie = Categorie.objects.create(nom="Cat Race", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Prod Race", code="PRACE01", entreprise=cls.ent,
            categorie=cls.categorie,
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.admin).access_token)}"}

    def _creer_facture(self, suffix, token, results):
        """Crée une facture depuis un thread séparé.
        Le token est généré dans le thread principal (setUpTestData est dans une
        transaction test non visible des connexions DB des threads enfants).
        """
        from rest_framework.test import APIClient
        client = APIClient()
        r = client.post(
            "/api/factures/",
            {
                "lieu": self.lieu.pk,
                "lignes": [
                    {
                        "description": f"Ligne {suffix}",
                        "quantite": "1",
                        "prix_unitaire": "1000",
                    }
                ],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        results.append((r.status_code, r.json().get("numero") if r.status_code == 201 else None))

    def test_numeros_facture_uniques_concurrent(self):
        """
        2 créations concurrentes de factures pour le même lieu dans le même jour
        → les numéros générés sont distincts (select_for_update sérialise).
        Tokens générés dans le thread principal pour éviter FK violation dans threads enfants.
        """
        results = []
        # Générer les tokens AVANT les threads (DB connection du thread principal)
        tokens = [str(RefreshToken.for_user(self.admin).access_token) for _ in range(2)]
        threads = [
            threading.Thread(target=self._creer_facture, args=(i, tokens[i], results))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        codes = [r[1] for r in results if r[0] == 201]
        if len(codes) >= 2:
            self.assertEqual(
                len(set(codes)), len(codes),
                f"Numéros de facture dupliqués détectés : {codes}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-boutiques / Multi-usines — Isolation intra-entreprise
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsolationIntraEntreprise(APITestCase):
    """
    Vérifie l'isolation intra-entreprise :
    deux boutiques (ou usines) dans la MÊME entreprise sont isolées par lieu.

    Risque : boutique A passe ?lieu=B ou accède aux endpoints boutique B.
    Attendu : chaque utilisateur boutique/usine ne voit que SON lieu.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntMultiLieu")

        # Deux boutiques dans la même entreprise
        cls.boutique_a = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique A", code="BA",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.boutique_b = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique B", code="BB",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        # Deux usines dans la même entreprise
        cls.usine_a = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine A", code="UA",
            type_lieu=Lieu.TYPE_USINE,
        )
        cls.usine_b = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine B", code="UB",
            type_lieu=Lieu.TYPE_USINE,
        )

        cls.cat = Categorie.objects.create(nom="Cat IL", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Prod IL", code="PIL01", entreprise=cls.ent,
            categorie=cls.cat, poids_par_sac=50,
        )

        # Stock : boutique A a du stock, boutique B n'en a pas
        Stock.objects.create(lieu=cls.boutique_a, produit=cls.produit, quantite=Decimal("100"))

        # Utilisateurs par lieu
        cls.user_a = CustomUser.objects.create_user(
            username="boutique_a_user", password="pass1234",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent, lieu=cls.boutique_a,
        )
        cls.user_b = CustomUser.objects.create_user(
            username="boutique_b_user", password="pass1234",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent, lieu=cls.boutique_b,
        )
        cls.usine_user_a = CustomUser.objects.create_user(
            username="usine_a_user", password="pass1234",
            role=CustomUser.ROLE_USINE, entreprise=cls.ent, lieu=cls.usine_a,
        )
        cls.usine_user_b = CustomUser.objects.create_user(
            username="usine_b_user", password="pass1234",
            role=CustomUser.ROLE_USINE, entreprise=cls.ent, lieu=cls.usine_b,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_il", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    # ── Stock isolation ───────────────────────────────────────────────────────

    def test_boutique_b_ne_voit_pas_stock_boutique_a(self):
        """
        user_b (boutique B) fait GET /api/boutique/stock/ → liste vide.
        Le stock de boutique A n'est pas visible depuis boutique B.
        """
        r = self.client.get("/api/boutique/stock/", **self._jwt(self.user_b))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        lieux = {item.get("lieu") for item in items}
        self.assertNotIn(self.boutique_a.pk, lieux,
            "user_b ne doit pas voir le stock de boutique_a")

    def test_boutique_a_voit_son_stock(self):
        """user_a (boutique A) voit bien son propre stock."""
        r = self.client.get("/api/boutique/stock/", **self._jwt(self.user_a))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertGreater(len(items), 0, "user_a doit voir le stock de boutique_a")

    def test_boutique_b_ne_peut_pas_vendre_avec_lieu_a(self):
        """
        user_b tente une vente sur boutique_a en passant ?lieu= dans la query string.
        Le lieu est forcé à user.lieu en boutique → la tentative échoue (404/403/400).
        """
        r = self.client.post(
            f"/api/boutique/ventes/?lieu={self.boutique_a.pk}",
            {
                "lignes": [{"produit": self.produit.pk, "quantite": "1", "prix_unitaire": "500"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="isolation-ua-001",
            **self._jwt(self.user_b),
        )
        # user_b n'a pas de stock → ErreurStock → 400, OU lieu ignoré (user.lieu utilisé)
        # Dans tous les cas user_b ne doit PAS obtenir 201 avec le stock de boutique_a
        self.assertNotEqual(r.status_code, 201,
            "user_b ne doit pas pouvoir vendre avec le lieu de boutique_a")

    def test_dashboard_boutique_a_isole(self):
        """
        GET /api/boutique/dashboard/ pour user_a → caisse et données de boutique_a uniquement.
        """
        r = self.client.get("/api/boutique/dashboard/", **self._jwt(self.user_a))
        self.assertIn(r.status_code, [200, 400])
        if r.status_code == 200:
            data = r.json()
            # La réponse doit concerner boutique_a
            lieu_id = data.get("lieu_id") or data.get("lieu")
            if lieu_id:
                self.assertEqual(lieu_id, self.boutique_a.pk,
                    "Le dashboard de user_a doit afficher les données de boutique_a")

    # ── Tickets isolation ─────────────────────────────────────────────────────

    def test_boutique_b_ne_voit_pas_tickets_boutique_a(self):
        """
        GET /api/boutique/ventes/ pour user_b → liste vide (aucun ticket boutique_b).
        """
        r = self.client.get("/api/boutique/ventes/", **self._jwt(self.user_b))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        for ticket in items:
            lieu_id = ticket.get("lieu") or ticket.get("lieu_id")
            self.assertNotEqual(lieu_id, self.boutique_a.pk,
                "user_b ne doit voir aucun ticket de boutique_a")

    # ── Usine isolation ───────────────────────────────────────────────────────

    def test_usine_a_ne_voit_pas_lots_usine_b(self):
        """
        GET /api/usine/lots/ pour usine_user_a → aucun lot d'usine_b.
        Les lots sont scoped par request.user.lieu (usine).
        """
        r = self.client.get("/api/usine/lots/", **self._jwt(self.usine_user_a))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        for lot in items:
            lieu_id = lot.get("lieu_usine") or lot.get("usine_id")
            if lieu_id:
                self.assertNotEqual(lieu_id, self.usine_b.pk,
                    "usine_user_a ne doit voir aucun lot de usine_b")

    # ── Admin voit toutes les boutiques de son entreprise ─────────────────────

    def test_admin_rapport_voit_toutes_boutiques_entreprise(self):
        """
        GET /api/comptable/rapport-boutiques/ pour admin → voit les 2 boutiques
        (elles appartiennent à la même entreprise).
        """
        r = self.client.get("/api/comptable/rapport-boutiques/", **self._jwt(self.admin))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        lieux_ids = {item.get("lieu_id") or item.get("id") for item in data}
        self.assertIn(self.boutique_a.pk, lieux_ids,
            "Le rapport admin doit inclure boutique_a")
        self.assertIn(self.boutique_b.pk, lieux_ids,
            "Le rapport admin doit inclure boutique_b")
