"""
Tests finance KONIS — Payables, Créances, Emprunts, Caisse, Projets.

Couvre :
  A. Journal payable : création, paiement partiel, paiement total, verrouillage
  B. Journal créance : création, paiement reçu, soldage
  C. Emprunt : création, remboursement partiel, remboursement complet
  D. Caisse suprême : dépôt, retrait, solde insuffisant
  E. Projet : création, dépense, dépôt supplémentaire
  F. Règles métier : paiement excessif, journal soldé, taux intérêt max
  G. CheckConstraints DB : montants négatifs/zéro rejetés
  H. Isolation tenant : une entreprise ne voit pas les données d'une autre
  I. Caisse physique boutique : formule, collecte bloquée si dépassement, modifier_collecte
  J. Retrancher caisse (correction créance) : service + API + droits + contrainte DB
  K. Idempotency JournalCreance : double-tap avec même clé → 1 seul journal
  L. Endpoint caisse-disponible
"""
from decimal import Decimal

import datetime

from django.test import TestCase
from django.utils.timezone import now as tz_now
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import status

from core.models import CustomUser, Entreprise, Lieu
from finance.models import (
    CaisseSupremeTransaction,
    Creancier,
    ClientFinance,
    Emprunt,
    JournalCreance,
    JournalPayable,
    Projet,
)
from django.test import override_settings
from django.db import IntegrityError

from finance.models import CollecteArgent
from finance.services import (
    ErreurFinance,
    JournalSoldeError,
    PaiementExcessifError,
    SoldeInsuffisantError,
    creer_emprunt,
    creer_journal_creance,
    creer_journal_payable,
    creer_projet,
    enregistrer_collecte,
    enregistrer_depot_projet,
    enregistrer_depense_projet,
    enregistrer_paiement_creance,
    enregistrer_paiement_payable,
    enregistrer_remboursement,
    enregistrer_transaction_caisse,
    get_caisse_physique_boutique,
    get_solde_caisse,
    modifier_collecte,
    solder_journal_payable,
)
from produits.models import Produit
from ventes.models import Ticket


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _setup():
    ent = Entreprise.objects.create(nom="KONIS Finance Test")
    lieu = Lieu.objects.create(entreprise=ent, nom="HQ", type_lieu=Lieu.TYPE_MAGASIN, code="HQ")
    user = CustomUser.objects.create_user(
        username="daf_test", password="daf12345",
        role=CustomUser.ROLE_DAF, entreprise=ent, lieu=lieu,
    )
    creancier = Creancier.objects.create(
        entreprise=ent, nom="Fournisseur A", type_creancier="fournisseur"
    )
    client = ClientFinance.objects.create(entreprise=ent, nom="Client B")
    return ent, lieu, user, creancier, client


# ── A. Journal Payable ────────────────────────────────────────────────────────

class TestJournalPayable(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.lieu, cls.user, cls.creancier, _ = _setup()

    def _journal(self, montant="50000"):
        return creer_journal_payable(
            creancier=self.creancier,
            description="Facture fournisseur",
            montant_initial=Decimal(montant),
            created_by=self.user,
        )

    def test_creation_journal_payable(self):
        """Journal créé avec montant_paye=0 et statut en_cours."""
        j = self._journal()
        self.assertIsNotNone(j.pk)
        self.assertEqual(j.montant_initial, Decimal("50000"))
        self.assertEqual(j.montant_paye, Decimal("0"))
        self.assertEqual(j.statut, "en_cours")
        self.assertIsNone(j.locked_at)

    def test_montant_restant_initial(self):
        """montant_restant == montant_initial avant tout paiement."""
        j = self._journal("75000")
        self.assertEqual(j.montant_restant, Decimal("75000"))

    def test_paiement_partiel_met_a_jour_montant_paye(self):
        """Un paiement partiel incrémente montant_paye sans solder."""
        j = self._journal("100000")
        enregistrer_paiement_payable(journal=j, montant=Decimal("40000"), date=datetime.date.today(), created_by=self.user)
        j.refresh_from_db()
        self.assertEqual(j.montant_paye, Decimal("40000"))
        self.assertEqual(j.montant_restant, Decimal("60000"))
        self.assertEqual(j.statut, "en_cours")
        self.assertIsNone(j.locked_at)

    def test_paiement_total_solde_le_journal(self):
        """Un paiement égal au montant total solde et verrouille le journal."""
        j = self._journal("30000")
        enregistrer_paiement_payable(journal=j, montant=Decimal("30000"), date=datetime.date.today(), created_by=self.user)
        j.refresh_from_db()
        self.assertEqual(j.statut, "solde")
        self.assertIsNotNone(j.locked_at)
        self.assertEqual(j.montant_restant, Decimal("0"))

    def test_paiement_excessif_leve_erreur(self):
        """Un paiement > montant_restant lève PaiementExcessifError."""
        j = self._journal("20000")
        with self.assertRaises(PaiementExcessifError):
            enregistrer_paiement_payable(journal=j, montant=Decimal("99999"), date=datetime.date.today(), created_by=self.user)

    def test_paiement_sur_journal_solde_leve_erreur(self):
        """Toute écriture sur un journal soldé lève JournalSoldeError."""
        j = self._journal("10000")
        enregistrer_paiement_payable(journal=j, montant=Decimal("10000"), date=datetime.date.today(), created_by=self.user)
        with self.assertRaises(JournalSoldeError):
            enregistrer_paiement_payable(journal=j, montant=Decimal("1"), date=datetime.date.today(), created_by=self.user)

    def test_solder_manuel_verrouille_journal(self):
        """Soldage manuel → statut=soldé, locked_at posé."""
        j = self._journal("50000")
        solder_journal_payable(journal=j, created_by=self.user)
        j.refresh_from_db()
        self.assertEqual(j.statut, "solde")
        self.assertIsNotNone(j.locked_at)


# ── B. Journal Créance ───────────────────────────────────────────────────────

class TestJournalCreance(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.lieu, cls.user, _, cls.client_finance = _setup()

    def _journal(self, montant="80000"):
        return creer_journal_creance(
            client=self.client_finance,
            description="Vente à crédit",
            montant_initial=Decimal(montant),
            created_by=self.user,
        )

    def test_creation_journal_creance(self):
        j = self._journal()
        self.assertIsNotNone(j.pk)
        self.assertEqual(j.statut, "en_cours")
        self.assertEqual(j.montant_paye, Decimal("0"))

    def test_paiement_partiel(self):
        j = self._journal("60000")
        enregistrer_paiement_creance(journal=j, montant=Decimal("25000"), date=datetime.date.today(), created_by=self.user)
        j.refresh_from_db()
        self.assertEqual(j.montant_paye, Decimal("25000"))
        self.assertEqual(j.statut, "en_cours")

    def test_paiement_total_solde(self):
        j = self._journal("60000")
        enregistrer_paiement_creance(journal=j, montant=Decimal("60000"), date=datetime.date.today(), created_by=self.user)
        j.refresh_from_db()
        self.assertEqual(j.statut, "solde")
        self.assertIsNotNone(j.locked_at)

    def test_paiement_excessif_leve_erreur(self):
        j = self._journal("10000")
        with self.assertRaises(PaiementExcessifError):
            enregistrer_paiement_creance(journal=j, montant=Decimal("50000"), date=datetime.date.today(), created_by=self.user)

    def test_montant_restant_coherent(self):
        """montant_restant = montant_initial - montant_paye (propriété calculée)."""
        j = self._journal("100000")
        enregistrer_paiement_creance(journal=j, montant=Decimal("35000"), date=datetime.date.today(), created_by=self.user)
        j.refresh_from_db()
        self.assertEqual(j.montant_restant, Decimal("65000"))


# ── C. Emprunt ───────────────────────────────────────────────────────────────

class TestEmprunt(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.lieu, cls.user, _, _ = _setup()

    def _emprunt(self, montant="500000"):
        from django.utils.timezone import now
        return creer_emprunt(
            entreprise=self.ent,
            nom="Prêt BNI",
            banque="BNI",
            montant_initial=Decimal(montant),
            date_debut=now().date(),
            created_by=self.user,
        )

    def test_creation_emprunt(self):
        e = self._emprunt()
        self.assertEqual(e.statut, "en_cours")
        self.assertEqual(e.montant_rembourse, Decimal("0"))

    def test_remboursement_partiel(self):
        e = self._emprunt("200000")
        enregistrer_remboursement(emprunt=e, montant=Decimal("80000"), date=datetime.date.today(), created_by=self.user)
        e.refresh_from_db()
        self.assertEqual(e.montant_rembourse, Decimal("80000"))
        self.assertEqual(e.statut, "en_cours")

    def test_remboursement_complet_change_statut(self):
        e = self._emprunt("100000")
        enregistrer_remboursement(emprunt=e, montant=Decimal("100000"), date=datetime.date.today(), created_by=self.user)
        e.refresh_from_db()
        self.assertEqual(e.statut, "rembourse")

    def test_remboursement_excessif_leve_erreur(self):
        e = self._emprunt("50000")
        with self.assertRaises(ErreurFinance):
            enregistrer_remboursement(emprunt=e, montant=Decimal("999999"), date=datetime.date.today(), created_by=self.user)


# ── D. Caisse Suprême ─────────────────────────────────────────────────────────

class TestCaisseSupreme(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.lieu, cls.user, _, _ = _setup()

    def test_depot_augmente_solde(self):
        solde_avant = get_solde_caisse(self.ent)
        enregistrer_transaction_caisse(
            entreprise=self.ent,
            type_transaction="depot",
            montant=Decimal("100000"),
            description="Dépôt initial",
            date=datetime.date.today(),
            created_by=self.user,
        )
        self.assertEqual(get_solde_caisse(self.ent), solde_avant + Decimal("100000"))

    def test_retrait_diminue_solde(self):
        enregistrer_transaction_caisse(
            entreprise=self.ent,
            type_transaction="depot",
            montant=Decimal("200000"),
            description="Fonds",
            date=datetime.date.today(),
            created_by=self.user,
        )
        solde_avant = get_solde_caisse(self.ent)
        enregistrer_transaction_caisse(
            entreprise=self.ent,
            type_transaction="retrait",
            montant=Decimal("50000"),
            description="Achat matériel",
            date=datetime.date.today(),
            created_by=self.user,
        )
        self.assertEqual(get_solde_caisse(self.ent), solde_avant - Decimal("50000"))

    def test_retrait_insuffisant_leve_erreur(self):
        """Retrait supérieur au solde disponible lève SoldeInsuffisantError."""
        with self.assertRaises(SoldeInsuffisantError):
            enregistrer_transaction_caisse(
                entreprise=self.ent,
                type_transaction="retrait",
                montant=Decimal("99999999"),
                description="Retrait massif",
                date=datetime.date.today(),
                created_by=self.user,
            )


# ── E. Projet ─────────────────────────────────────────────────────────────────

class TestProjet(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.lieu, cls.user, _, _ = _setup()

    def _projet(self, budget="1000000"):
        from django.utils.timezone import now
        return creer_projet(
            entreprise=self.ent,
            nom="Projet Construction",
            budget_initial=Decimal(budget),
            date_debut=now().date(),
            created_by=self.user,
        )

    def test_creation_projet(self):
        p = self._projet()
        self.assertEqual(p.statut, "en_cours")
        self.assertEqual(p.budget_initial, Decimal("1000000"))

    def test_depense_projet_enregistree(self):
        p = self._projet()
        enregistrer_depense_projet(
            projet=p,
            montant=Decimal("150000"),
            description="Achat matériaux",
            date=datetime.date.today(),
            created_by=self.user,
        )
        self.assertEqual(p.depenses.count(), 1)
        self.assertEqual(p.depenses.first().montant, Decimal("150000"))

    def test_depot_supplementaire(self):
        p = self._projet()
        enregistrer_depot_projet(
            projet=p,
            montant=Decimal("500000"),
            description="Fonds supplémentaires",
            date=datetime.date.today(),
            created_by=self.user,
        )
        self.assertEqual(p.depots.count(), 1)


# ── F. CheckConstraints DB ────────────────────────────────────────────────────

class TestFinanceDBConstraints(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.lieu, cls.user, cls.creancier, cls.client_finance = _setup()

    def test_journal_payable_montant_negatif_rejete(self):
        """montant_initial < 0.01 → IntegrityError au niveau DB."""
        from django.db import IntegrityError
        with self.assertRaises((IntegrityError, Exception)):
            JournalPayable.objects.create(
                creancier=self.creancier,
                description="Test",
                montant_initial=Decimal("0"),
                montant_paye=Decimal("0"),
                created_by=self.user,
            )

    def test_journal_creance_montant_negatif_rejete(self):
        """montant_initial = 0 → rejeté par CheckConstraint."""
        from django.db import IntegrityError
        with self.assertRaises((IntegrityError, Exception)):
            JournalCreance.objects.create(
                client=self.client_finance,
                description="Test",
                montant_initial=Decimal("0"),
                montant_paye=Decimal("0"),
                created_by=self.user,
            )

    def test_emprunt_taux_negatif_rejete_par_service(self):
        """taux_interet < 0 → ErreurFinance (service valide avant DB)."""
        from django.utils.timezone import now
        with self.assertRaises(Exception):
            creer_emprunt(
                entreprise=self.ent,
                nom="Prêt test",
                banque="Banque X",
                montant_initial=Decimal("100000"),
                date_debut=now().date(),
                created_by=self.user,
                taux_interet=Decimal("-5"),
            )


# ── G. Isolation multi-tenant ─────────────────────────────────────────────────

class TestFinanceIsolation(APITestCase):
    """Un DAF de l'entreprise A ne voit pas les données de l'entreprise B."""

    @classmethod
    def setUpTestData(cls):
        cls.ent_a, _, cls.user_a, cls.creancier_a, _ = _setup()
        cls.ent_b = Entreprise.objects.create(nom="Entreprise B Finance")
        lieu_b = Lieu.objects.create(entreprise=cls.ent_b, nom="HQ B", type_lieu=Lieu.TYPE_MAGASIN, code="HQB")
        cls.user_b = CustomUser.objects.create_user(
            username="daf_b", password="dafB12345",
            role=CustomUser.ROLE_DAF, entreprise=cls.ent_b, lieu=lieu_b,
        )

        # Journal appartenant à ent_a
        cls.journal_a = creer_journal_payable(
            creancier=cls.creancier_a,
            description="Dette A",
            montant_initial=Decimal("50000"),
            created_by=cls.user_a,
        )

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def test_user_b_ne_voit_pas_journaux_ent_a(self):
        """user_b ne doit pas voir les journaux de l'entreprise A."""
        r = self.client.get("/api/finance/journaux-payables/", **self._jwt(self.user_b))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in r.json().get("results", r.json())]
        self.assertNotIn(self.journal_a.pk, ids)

    def test_user_a_voit_son_journal(self):
        """user_a voit ses propres journaux."""
        r = self.client.get("/api/finance/journaux-payables/", **self._jwt(self.user_a))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in r.json().get("results", r.json())]
        self.assertIn(self.journal_a.pk, ids)


# ── I. Caisse physique boutique ───────────────────────────────────────────────

class TestCaissePhysique(TestCase):
    """
    Vérifie la formule get_caisse_physique_boutique et les validations de collecte.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntCaisse")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique C", code="BC", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.user = CustomUser.objects.create_user(
            username="daf_caisse", password="pass1234",
            role=CustomUser.ROLE_DAF, entreprise=cls.ent, lieu=cls.lieu,
        )
        cls.produit = Produit.objects.create(
            nom="Café 1kg", code="C1KG", unite="kg", entreprise=cls.ent
        )

    def _ticket_cash(self, montant):
        numero = f"T-CAISSE-{Ticket.objects.filter(lieu=self.lieu).count() + 1}"
        return Ticket.objects.create(
            lieu=self.lieu,
            date=datetime.date.today(),
            numero=numero,
            montant_total=Decimal(str(montant)),
            montant_cash=Decimal(str(montant)),
        )

    def _collecte(self, montant_trouve, montant_pris):
        return enregistrer_collecte(
            lieu=self.lieu,
            date_collecte=datetime.date.today(),
            montant_trouve=Decimal(str(montant_trouve)),
            montant_pris=Decimal(str(montant_pris)),
            created_by=self.user,
        )

    def test_caisse_vide_sans_tickets(self):
        self.assertEqual(get_caisse_physique_boutique(self.lieu), Decimal("0"))

    def test_caisse_apres_ticket_cash(self):
        self._ticket_cash(10000)
        self.assertEqual(get_caisse_physique_boutique(self.lieu), Decimal("10000"))

    def test_caisse_diminue_apres_collecte(self):
        self._ticket_cash(10000)
        self._collecte(10000, 8000)
        self.assertEqual(get_caisse_physique_boutique(self.lieu), Decimal("2000"))

    def test_collecte_bloquee_si_depasse_caisse(self):
        # caisse_dispo = 5000, montant_trouve = 7000 (>= montant_pris), montant_pris = 6000 > caisse_dispo
        self._ticket_cash(5000)
        with self.assertRaises(ErreurFinance) as ctx:
            self._collecte(7000, 6000)
        self.assertIn("caisse disponible", str(ctx.exception).lower())

    def test_modifier_collecte_bloquee_si_depasse_caisse(self):
        self._ticket_cash(5000)
        collecte = self._collecte(5000, 3000)
        # La caisse disponible restante = 5000 - 3000 = 2000
        # Si on veut prendre 4500 (> 5000-3000+3000=5000 ok mais >5000 non)
        # caisse_avant = get_caisse() + ancien_pris = 2000 + 3000 = 5000 → ok
        # montant_pris = 5001 > 5000 → refus
        with self.assertRaises(ErreurFinance):
            modifier_collecte(
                collecte=collecte,
                updated_by=self.user,
                montant_pris=Decimal("5001"),
            )

    def test_modifier_collecte_autorise_dans_la_limite(self):
        self._ticket_cash(5000)
        collecte = self._collecte(5000, 3000)
        # caisse_avant = 2000 + 3000 = 5000 → 4999 autorisé
        result = modifier_collecte(
            collecte=collecte,
            updated_by=self.user,
            montant_pris=Decimal("4999"),
        )
        self.assertEqual(result.montant_pris, Decimal("4999"))


# ── J. Retrancher caisse (correction créance) ─────────────────────────────────

class TestRetracherCaisse(APITestCase):
    """
    Vérifie le service creer_journal_creance(retrancher_caisse=True) et les gardes API.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntRetranch")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="BoutiqueR", code="BR", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.lieu_col = Lieu.objects.create(
            entreprise=cls.ent, nom="BoutiqueR2", code="BR2", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_ret", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent, lieu=cls.lieu,
        )
        cls.collecteur = CustomUser.objects.create_user(
            username="col_ret", password="pass1234",
            role=CustomUser.ROLE_COLLECTEUR, entreprise=cls.ent, lieu=cls.lieu_col,
        )
        cls.client_fin = ClientFinance.objects.create(entreprise=cls.ent, nom="ClientR")
        cls.produit = Produit.objects.create(
            nom="Café R", code="CR01", unite="kg", entreprise=cls.ent
        )

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    def _ajouter_cash(self, montant):
        numero = f"T-RET-{Ticket.objects.filter(lieu=self.lieu).count() + 1}"
        Ticket.objects.create(
            lieu=self.lieu,
            date=datetime.date.today(),
            numero=numero,
            montant_total=Decimal(str(montant)),
            montant_cash=Decimal(str(montant)),
        )

    def test_retrancher_caisse_reduit_caisse_physique(self):
        self._ajouter_cash(20000)
        caisse_avant = get_caisse_physique_boutique(self.lieu)
        creer_journal_creance(
            client=self.client_fin,
            description="Correction vente cash",
            montant_initial=Decimal("5000"),
            created_by=self.admin,
            lieu=self.lieu,
            retrancher_caisse=True,
        )
        caisse_apres = get_caisse_physique_boutique(self.lieu)
        self.assertEqual(caisse_avant - caisse_apres, Decimal("5000"))

    def test_retrancher_caisse_bloque_si_insuffisante(self):
        # caisse = 0 → impossible de retrancher 1000
        with self.assertRaises(ErreurFinance) as ctx:
            creer_journal_creance(
                client=self.client_fin,
                description="Mauvaise correction",
                montant_initial=Decimal("1000"),
                created_by=self.admin,
                lieu=self.lieu,
                retrancher_caisse=True,
            )
        self.assertIn("caisse disponible", str(ctx.exception).lower())

    def test_api_collecteur_ne_peut_pas_retrancher(self):
        """Un collecteur ne peut pas cocher retrancher_caisse via l'API."""
        r = self.client.post(
            "/api/finance/journaux-creances/",
            {
                "client_id": self.client_fin.pk,
                "description": "Test",
                "montant_initial": "1000.00",
                "retrancher_caisse": True,
                "lieu_id": self.lieu.pk,
            },
            format="json",
            **self._jwt(self.collecteur),
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_admin_peut_retrancher(self):
        """Un admin peut créer un journal créance avec retrancher_caisse=True si caisse suffisante."""
        self._ajouter_cash(30000)
        r = self.client.post(
            "/api/finance/journaux-creances/",
            {
                "client_id": self.client_fin.pk,
                "description": "Correction vente",
                "montant_initial": "10000.00",
                "retrancher_caisse": True,
                "lieu_id": self.lieu.pk,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="test-retranch-admin-001",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.json())
        self.assertEqual(Decimal(r.json()["correction_caisse"]), Decimal("10000.00"))

    def test_db_constraint_correction_superieure_montant_initial(self):
        """La DB rejette correction_caisse > montant_initial."""
        with self.assertRaises(IntegrityError):
            JournalCreance.objects.create(
                client=self.client_fin,
                description="Test contrainte",
                montant_initial=Decimal("1000"),
                montant_paye=Decimal("0"),
                correction_caisse=Decimal("1001"),  # > montant_initial
                created_by=self.admin,
                statut="en_cours",
            )


# ── K. Idempotency JournalCreance ─────────────────────────────────────────────

class TestIdempotencyJournalCreance(APITestCase):
    """
    Double-tap sur POST /api/finance/journaux-creances/ avec même Idempotency-Key
    → 1 seul journal créé (anti double-débit quand retrancher_caisse=True).
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntIdemCreance")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="BoutiqueI", code="BI", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_idem_cr", password="pass1234",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent, lieu=cls.lieu,
        )
        cls.client_fin = ClientFinance.objects.create(entreprise=cls.ent, nom="ClientI")
        Ticket.objects.create(
            lieu=cls.lieu,
            date=datetime.date.today(),
            numero="T-IDEM-001",
            montant_total=Decimal("50000"),
            montant_cash=Decimal("50000"),
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.admin).access_token)}"}

    def _post(self, key=None):
        headers = self._jwt()
        if key:
            headers["HTTP_IDEMPOTENCY_KEY"] = key
        return self.client.post(
            "/api/finance/journaux-creances/",
            {
                "client_id": self.client_fin.pk,
                "description": "Créance idempotente",
                "montant_initial": "10000.00",
                "retrancher_caisse": True,
                "lieu_id": self.lieu.pk,
            },
            format="json",
            **headers,
        )

    def test_double_tap_meme_cle_cree_un_seul_journal(self):
        key = "idem-creance-001"
        r1 = self._post(key)
        r2 = self._post(key)
        self.assertIn(r1.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.json()["id"], r2.json()["id"])

    def test_double_tap_meme_cle_une_seule_correction_caisse(self):
        key = "idem-creance-002"
        caisse_avant = get_caisse_physique_boutique(self.lieu)
        self._post(key)
        self._post(key)
        caisse_apres = get_caisse_physique_boutique(self.lieu)
        # Exactement 10000 soustrait (pas 20000)
        self.assertEqual(caisse_avant - caisse_apres, Decimal("10000"))

    @override_settings(IDEMPOTENCY_STRICT_MODE=False)
    def test_sans_cle_deux_journaux_distincts(self):
        r1 = self._post()
        r2 = self._post()
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(r1.json()["id"], r2.json()["id"])


# ── L. Endpoint caisse-disponible ─────────────────────────────────────────────

class TestCaisseDisponibleEndpoint(APITestCase):
    """GET /api/finance/collectes/caisse-disponible/?lieu_id=X"""

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntCaisseEP")
        cls.lieu = Lieu.objects.create(
            entreprise=cls.ent, nom="BoutiqueEP", code="EP", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.collecteur = CustomUser.objects.create_user(
            username="col_ep", password="pass1234",
            role=CustomUser.ROLE_COLLECTEUR, entreprise=cls.ent, lieu=cls.lieu,
        )
        Ticket.objects.create(
            lieu=cls.lieu,
            date=datetime.date.today(),
            numero="T-EP-001",
            montant_total=Decimal("15000"),
            montant_cash=Decimal("15000"),
        )

    def _jwt(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(self.collecteur).access_token)}"}

    def test_retourne_caisse_disponible(self):
        r = self.client.get(
            f"/api/finance/collectes/caisse-disponible/?lieu_id={self.lieu.pk}",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        self.assertEqual(data["lieu_id"], self.lieu.pk)
        self.assertEqual(Decimal(data["caisse_disponible"]), Decimal("15000"))

    def test_lieu_id_manquant_retourne_400(self):
        r = self.client.get("/api/finance/collectes/caisse-disponible/", **self._jwt())
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lieu_autre_entreprise_retourne_404(self):
        ent2 = Entreprise.objects.create(nom="EntAutre")
        lieu2 = Lieu.objects.create(
            entreprise=ent2, nom="AutreBoutique", code="AU", type_lieu=Lieu.TYPE_MAGASIN
        )
        r = self.client.get(
            f"/api/finance/collectes/caisse-disponible/?lieu_id={lieu2.pk}",
            **self._jwt(),
        )
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
