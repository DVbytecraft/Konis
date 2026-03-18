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
from finance.services import (
    ErreurFinance,
    JournalSoldeError,
    PaiementExcessifError,
    SoldeInsuffisantError,
    creer_emprunt,
    creer_journal_creance,
    creer_journal_payable,
    creer_projet,
    enregistrer_depot_projet,
    enregistrer_depense_projet,
    enregistrer_paiement_creance,
    enregistrer_paiement_payable,
    enregistrer_remboursement,
    enregistrer_transaction_caisse,
    get_solde_caisse,
    solder_journal_payable,
)


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
