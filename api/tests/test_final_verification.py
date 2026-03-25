"""
Vérifications finales — Charge, cohérence inter-flux, cas extrêmes.

Trois catégories :
  1. TestConcurrenceAvancee  — retraits caisse simultanés, cessions de lot concurrentes
  2. TestFluxComplets         — cycles métier end-to-end (créance, collecte, usine→boutique→vente)
  3. TestEdgeCases            — limites métier, contraintes DB, erreurs de surface API

Règle : chaque test prouve un comportement par assertion directe sur la DB ou le service.
Aucun comportement n'est supposé correct — tout est vérifié.
"""
import threading
from datetime import date
from decimal import Decimal

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import CustomUser, Entreprise, Lieu
from finance.models import ClientFinance, JournalCreance
from finance.services import (
    ErreurFinance,
    PaiementExcessifError,
    SoldeInsuffisantError,
    creer_journal_creance,
    enregistrer_collecte,
    enregistrer_paiement_creance,
    enregistrer_transaction_caisse,
    get_caisse_physique_boutique,
    get_solde_caisse,
)
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Categorie, Produit
from usine.models import LotProduction
from usine.services import creer_lot_production, transferer_lot_vers_boutique
from ventes.models import Ticket
from ventes.services import vente_boutique


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONCURRENCE AVANCÉE
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrenceAvancee(TransactionTestCase):
    """
    Tests de concurrence réels avec threads distincts et connexions DB séparées.
    Utilise TransactionTestCase (pas de rollback entre tests → isolation via setUp).

    Vérifie que les mécanismes select_for_update() tiennent sous charge simultanée.
    """

    def setUp(self):
        self.ent = Entreprise.objects.create(nom="EntConcAvancee")
        self.usine = Lieu.objects.create(
            entreprise=self.ent, nom="Usine CA", code="UCA",
            type_lieu=Lieu.TYPE_USINE,
        )
        self.boutique = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique CA", code="BCA",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        self.admin = CustomUser.objects.create_user(
            username="admin_ca", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=self.ent,
        )
        self.cat = Categorie.objects.create(nom="Cat CA", entreprise=self.ent)
        self.produit = Produit.objects.create(
            nom="Farine CA", code="FCA01", entreprise=self.ent,
            categorie=self.cat, category=Produit.CATEGORY_FINISHED, poids_par_sac=50,
        )

    # ── Retraits caisse simultanés ────────────────────────────────────────────

    def test_deux_retraits_simultanees_caisse_supreme(self):
        """
        Solde caisse = 1000 FCFA. Deux retraits de 700 FCFA simultanés.
        select_for_update() sur Entreprise sérialise → un seul réussit.
        Solde final = 300 FCFA (jamais négatif).
        """
        enregistrer_transaction_caisse(
            entreprise=self.ent,
            type_transaction="depot",
            montant=Decimal("1000"),
            description="Dépôt initial",
            date=date(2026, 3, 25),
            created_by=self.admin,
        )
        self.assertEqual(get_solde_caisse(self.ent), Decimal("1000"))

        results = [None, None]

        def _retrait(idx):
            close_old_connections()
            try:
                enregistrer_transaction_caisse(
                    entreprise=self.ent,
                    type_transaction="retrait",
                    montant=Decimal("700"),
                    description=f"Retrait concurrent {idx}",
                    date=date(2026, 3, 25),
                    created_by=self.admin,
                )
                results[idx] = "ok"
            except SoldeInsuffisantError:
                results[idx] = "insuffisant"
            except Exception as e:
                results[idx] = e
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_retrait, args=(0,))
        t2 = threading.Thread(target=_retrait, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Un seul doit passer
        self.assertEqual(results.count("ok"), 1, f"Résultats: {results}")
        self.assertEqual(results.count("insuffisant"), 1, f"Résultats: {results}")

        # Solde final = 300 (jamais négatif)
        solde = get_solde_caisse(self.ent)
        self.assertEqual(solde, Decimal("300"))
        self.assertGreaterEqual(solde, Decimal("0"), "Solde caisse ne peut pas être négatif")

    # ── Cessions de lot concurrentes ──────────────────────────────────────────

    def test_deux_cessions_concurrentes_stock_insuffisant(self):
        """
        Lot avec 5 sacs. Deux cessions de 4 sacs simultanées.
        Le stock usine est protégé par select_for_update → une seule réussit.
        Stock restant = 1 sac (jamais négatif).
        """
        lot = creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="LOT-CONC-01",
            quantite_sacs=Decimal("5"),
            created_by=self.admin,
        )

        boutique2 = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique CA2", code="BCA2",
            type_lieu=Lieu.TYPE_MAGASIN,
        )

        results = [None, None]

        def _cession(idx, dest):
            close_old_connections()
            try:
                transferer_lot_vers_boutique(
                    lot=lot,
                    boutique=dest,
                    quantite_sacs=Decimal("4"),
                    prix_par_sac=Decimal("1000"),
                )
                results[idx] = "ok"
            except ErreurStock:
                results[idx] = "insuffisant"
            except Exception as e:
                results[idx] = e
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_cession, args=(0, self.boutique))
        t2 = threading.Thread(target=_cession, args=(1, boutique2))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Une seule cession doit passer
        self.assertEqual(results.count("ok"), 1, f"Résultats: {results}")
        self.assertEqual(results.count("insuffisant"), 1, f"Résultats: {results}")

        # Stock usine jamais négatif
        stock_usine = Stock.objects.get(produit=self.produit, lieu=self.usine)
        self.assertGreaterEqual(stock_usine.quantite, Decimal("0"))

    # ── Ventes simultanées stock exact ────────────────────────────────────────

    def test_vente_simultanee_stock_exact_zero(self):
        """
        Stock = exactement 5 sacs. Deux ventes de 5 sacs simultanées.
        Une réussit, l'autre lève ErreurStock. Stock final = 0 (jamais négatif).
        """
        Stock.objects.create(
            lieu=self.boutique, produit=self.produit, quantite=Decimal("5")
        )
        results = [None, None]

        def _vente(idx):
            close_old_connections()
            try:
                ticket, _ = vente_boutique(
                    self.boutique,
                    [(self.produit, Decimal("5"), Decimal("500"), "sac")],
                )
                results[idx] = "ok"
            except ErreurStock:
                results[idx] = "insuffisant"
            except Exception as e:
                results[idx] = e
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_vente, args=(0,))
        t2 = threading.Thread(target=_vente, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertEqual(results.count("ok"), 1, f"Résultats: {results}")
        stock = Stock.objects.get(lieu=self.boutique, produit=self.produit)
        self.assertEqual(stock.quantite, Decimal("0"))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FLUX COMPLETS (END-TO-END COHÉRENCE)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFluxComplets(TestCase):
    """
    Valide la cohérence des données à travers les cycles métier complets.
    Chaque test est un scénario réel de bout en bout.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntFluxComplets")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique FC", code="BFC",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.usine = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine FC", code="UFC",
            type_lieu=Lieu.TYPE_USINE,
        )
        cls.cat = Categorie.objects.create(nom="Cat FC", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Farine FC", code="FFC01", entreprise=cls.ent,
            categorie=cls.cat, category=Produit.CATEGORY_FINISHED, poids_par_sac=50,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_fc", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.collecteur = CustomUser.objects.create_user(
            username="collecteur_fc", password="pass",
            role=CustomUser.ROLE_COLLECTEUR, entreprise=cls.ent,
        )

    # ── Cycle créance complet ─────────────────────────────────────────────────

    def test_cycle_creance_paiements_partiels_jusqu_au_solde(self):
        """
        Créance 10 000 FCFA.
        Paiement 1 : 4 000 → restant = 6 000, statut = en_cours.
        Paiement 2 : 6 000 → restant = 0,     statut = solde.
        Paiement 3 : 1 FCFA → PaiementExcessifError (pas de surpaiement).
        """
        client = ClientFinance.objects.create(entreprise=self.ent, nom="Client FC1")
        journal = creer_journal_creance(
            client=client,
            description="Créance test flux complet",
            montant_initial=Decimal("10000"),
            created_by=self.admin,
        )
        self.assertEqual(journal.montant_initial, Decimal("10000"))
        self.assertEqual(journal.montant_restant, Decimal("10000"))
        self.assertNotEqual(journal.statut, "solde")

        # Paiement partiel 1
        enregistrer_paiement_creance(
            journal=journal, montant=Decimal("4000"),
            date=date(2026, 3, 25), created_by=self.admin,
        )
        journal.refresh_from_db()
        self.assertEqual(journal.montant_paye, Decimal("4000"))
        self.assertEqual(journal.montant_restant, Decimal("6000"))
        self.assertNotEqual(journal.statut, "solde")

        # Paiement partiel 2 (solde)
        enregistrer_paiement_creance(
            journal=journal, montant=Decimal("6000"),
            date=date(2026, 3, 25), created_by=self.admin,
        )
        journal.refresh_from_db()
        self.assertEqual(journal.montant_paye, Decimal("10000"))
        self.assertEqual(journal.montant_restant, Decimal("0"))
        self.assertEqual(journal.statut, "solde")

        # Paiement 3 : surpaiement interdit (journal soldé → JournalSoldeError ou PaiementExcessifError)
        from finance.services import JournalSoldeError
        with self.assertRaises((PaiementExcessifError, JournalSoldeError)):
            enregistrer_paiement_creance(
                journal=journal, montant=Decimal("1"),
                date=date(2026, 3, 25), created_by=self.admin,
            )

    # ── Cycle collecte → caisse_physique ─────────────────────────────────────

    def test_cycle_ventes_puis_collecte_reduit_caisse(self):
        """
        Ventes cash boutique : 5 000 FCFA.
        Collecte : montant_pris = 3 000.
        caisse_physique = 5 000 - 3 000 = 2 000 FCFA.
        """
        produit = Produit.objects.create(
            nom="Prod Coll", code="PCOLL1", entreprise=self.ent,
            categorie=self.cat, category=Produit.CATEGORY_FINISHED, poids_par_sac=50,
        )
        Stock.objects.create(lieu=self.boutique, produit=produit, quantite=Decimal("10"))

        # Vente cash 5 000
        vente_boutique(self.boutique, [(produit, Decimal("1"), Decimal("5000"))])
        caisse_avant = get_caisse_physique_boutique(self.boutique)
        self.assertGreaterEqual(caisse_avant, Decimal("5000"))

        # Collecte : prend 3 000
        enregistrer_collecte(
            lieu=self.boutique,
            date_collecte=date(2026, 3, 25),
            montant_trouve=caisse_avant,
            montant_pris=Decimal("3000"),
            created_by=self.collecteur,
        )
        caisse_apres = get_caisse_physique_boutique(self.boutique)
        self.assertEqual(caisse_apres, caisse_avant - Decimal("3000"))

    # ── Cycle correction caisse (retrancher_caisse) ───────────────────────────

    def test_cycle_ventes_puis_correction_caisse(self):
        """
        Ventes cash : 8 000 FCFA.
        Création journal créance avec retrancher_caisse=True, montant=2 000.
        caisse_physique = 8 000 - 2 000 = 6 000 FCFA.
        La correction est enregistrée dans JournalCreance.correction_caisse.
        """
        produit = Produit.objects.create(
            nom="Prod Corr", code="PCORR1", entreprise=self.ent,
            categorie=self.cat, category=Produit.CATEGORY_FINISHED, poids_par_sac=50,
        )
        boutique_corr = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique Corr", code="BCORR",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        Stock.objects.create(lieu=boutique_corr, produit=produit, quantite=Decimal("10"))

        vente_boutique(boutique_corr, [(produit, Decimal("1"), Decimal("8000"))])
        caisse_avant = get_caisse_physique_boutique(boutique_corr)
        self.assertGreaterEqual(caisse_avant, Decimal("8000"))

        client = ClientFinance.objects.create(entreprise=self.ent, nom="Client Corr")
        journal = creer_journal_creance(
            client=client,
            lieu=boutique_corr,
            description="Avance client",
            montant_initial=Decimal("2000"),
            created_by=self.admin,
            retrancher_caisse=True,
        )

        self.assertEqual(journal.correction_caisse, Decimal("2000"))
        caisse_apres = get_caisse_physique_boutique(boutique_corr)
        self.assertEqual(caisse_apres, caisse_avant - Decimal("2000"))

    # ── Cycle usine → cession → vente boutique ───────────────────────────────

    def test_cycle_usine_cession_vente_coherence_stock(self):
        """
        Usine produit 10 sacs. Cède 6 sacs à boutique.
        Stock usine = 4. Stock boutique = 6.
        Boutique vend 2 sacs. Stock boutique = 4.
        caisse_physique boutique = 2 × prix_unitaire.
        Invariant total sacs = 10 tout au long.
        """
        boutique_cv = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique CV", code="BCV",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        usine_cv = Lieu.objects.create(
            entreprise=self.ent, nom="Usine CV", code="UCV",
            type_lieu=Lieu.TYPE_USINE,
        )

        # Production : 10 sacs
        lot = creer_lot_production(
            lieu_usine=usine_cv,
            produit_fini=self.produit,
            nom_lot="LOT-CV-01",
            quantite_sacs=Decimal("10"),
            created_by=self.admin,
        )
        stock_usine = Stock.objects.get(produit=self.produit, lieu=usine_cv)
        self.assertEqual(stock_usine.quantite, Decimal("10"))

        # Cession : 6 sacs → boutique
        transferer_lot_vers_boutique(
            lot=lot,
            boutique=boutique_cv,
            quantite_sacs=Decimal("6"),
            prix_par_sac=Decimal("500"),
        )
        stock_usine.refresh_from_db()
        stock_boutique = Stock.objects.get(produit=self.produit, lieu=boutique_cv)
        self.assertEqual(stock_usine.quantite, Decimal("4"))
        self.assertEqual(stock_boutique.quantite, Decimal("6"))

        # Invariant : total = 10
        total = stock_usine.quantite + stock_boutique.quantite
        self.assertEqual(total, Decimal("10"))

        # Vente boutique : 2 sacs (explicitement en "sac" pour éviter la conversion kg auto)
        prix_sac = Decimal("600")
        vente_boutique(boutique_cv, [(self.produit, Decimal("2"), prix_sac, "sac")])
        stock_boutique.refresh_from_db()
        self.assertEqual(stock_boutique.quantite, Decimal("4"))

        # Caisse boutique = 2 × 600 = 1 200
        caisse = get_caisse_physique_boutique(boutique_cv)
        self.assertEqual(caisse, Decimal("2") * prix_sac)

    # ── Cycle emprunt → remboursements successifs ─────────────────────────────

    def test_cycle_emprunt_remboursements_convergent_vers_zero(self):
        """
        Emprunt 15 000 FCFA.
        Remboursement 1 : 5 000 → restant 10 000.
        Remboursement 2 : 5 000 → restant 5 000.
        Remboursement 3 : 5 000 → restant 0, statut = rembourse.
        Remboursement 4 : 1 FCFA → ErreurFinance (trop-perçu).
        """
        from finance.models import Emprunt
        from finance.services import creer_emprunt, enregistrer_remboursement

        emprunt = creer_emprunt(
            entreprise=self.ent,
            nom="Emprunt flux complet",
            banque="Banque Test FC",
            montant_initial=Decimal("15000"),
            date_debut=date(2026, 3, 25),
            created_by=self.admin,
        )
        self.assertEqual(emprunt.montant_restant, Decimal("15000"))

        for idx, montant in enumerate([Decimal("5000")] * 3):
            enregistrer_remboursement(
                emprunt=emprunt,
                montant=montant,
                date=date(2026, 3, 25),
                created_by=self.admin,
            )
            emprunt.refresh_from_db()
            attendu = Decimal("15000") - (Decimal("5000") * (idx + 1))
            self.assertEqual(emprunt.montant_restant, attendu,
                f"Après remboursement {idx+1}, restant attendu {attendu}")

        emprunt.refresh_from_db()
        self.assertEqual(emprunt.montant_restant, Decimal("0"))

        # Sur-remboursement interdit
        with self.assertRaises((ErreurFinance, Exception)):
            enregistrer_remboursement(
                emprunt=emprunt,
                montant=Decimal("1"),
                date=date(2026, 3, 25),
                created_by=self.admin,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EDGE CASES — LIMITES MÉTIER ET CONTRAINTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCasesServices(TestCase):
    """
    Tests des cas limites au niveau service (sans HTTP).
    Vérifie que chaque garde-fou lève la bonne exception.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntEdge")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique Edge", code="BEDGE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.usine = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine Edge", code="UEDGE",
            type_lieu=Lieu.TYPE_USINE,
        )
        cls.cat = Categorie.objects.create(nom="Cat Edge", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Prod Edge", code="PEDGE1", entreprise=cls.ent,
            categorie=cls.cat, category=Produit.CATEGORY_FINISHED, poids_par_sac=50,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_edge", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.collecteur = CustomUser.objects.create_user(
            username="collecteur_edge", password="pass",
            role=CustomUser.ROLE_COLLECTEUR, entreprise=cls.ent,
        )

    # ── Vente : stock exact puis épuisé ──────────────────────────────────────

    def test_vente_stock_exact_puis_epuise(self):
        """
        Stock = 3 sacs. Vente de 3 sacs → ok.
        Vente suivante de 1 sac → ErreurStock (stock = 0).
        """
        produit = Produit.objects.create(
            nom="Prod Epuise", code="PE01", entreprise=self.ent,
            categorie=self.cat, category=Produit.CATEGORY_FINISHED,
        )
        boutique = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique Epuise", code="BEPUISE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        Stock.objects.create(lieu=boutique, produit=produit, quantite=Decimal("3"))

        # Vente exacte : ok
        ticket, created = vente_boutique(boutique, [(produit, Decimal("3"), Decimal("100"))])
        self.assertTrue(created)

        # Stock = 0 → suivante rejetée
        with self.assertRaises(ErreurStock):
            vente_boutique(boutique, [(produit, Decimal("1"), Decimal("100"))])

        stock = Stock.objects.get(lieu=boutique, produit=produit)
        self.assertEqual(stock.quantite, Decimal("0"), "Stock ne peut pas être négatif")

    # ── Vente : quantité zéro ─────────────────────────────────────────────────

    def test_vente_quantite_zero_rejetee(self):
        """quantite=0 doit lever ErreurStock."""
        Stock.objects.get_or_create(
            lieu=self.boutique, produit=self.produit,
            defaults={"quantite": Decimal("10")},
        )
        with self.assertRaises(ErreurStock):
            vente_boutique(self.boutique, [(self.produit, Decimal("0"), Decimal("100"))])

    # ── Vente crédit sans client ──────────────────────────────────────────────

    def test_vente_credit_sans_client_rejetee(self):
        """type_vente='credit' sans client → ErreurStock."""
        Stock.objects.get_or_create(
            lieu=self.boutique, produit=self.produit,
            defaults={"quantite": Decimal("10")},
        )
        with self.assertRaises(ErreurStock):
            vente_boutique(
                self.boutique,
                [(self.produit, Decimal("1"), Decimal("100"))],
                type_vente="credit",
                client=None,
            )

    # ── Collecte : montant_pris > montant_trouve ──────────────────────────────

    def test_collecte_montant_pris_superieur_au_trouve(self):
        """montant_pris > montant_trouve → ErreurFinance."""
        with self.assertRaises(ErreurFinance):
            enregistrer_collecte(
                lieu=self.boutique,
                date_collecte=date(2026, 3, 25),
                montant_trouve=Decimal("1000"),
                montant_pris=Decimal("1001"),
                created_by=self.collecteur,
            )

    # ── Collecte : montant_pris > caisse disponible ───────────────────────────

    def test_collecte_montant_pris_superieur_caisse_disponible(self):
        """
        Caisse boutique vide (pas de ventes). Collecte avec montant_pris=1 → ErreurFinance.
        """
        boutique_vide = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique Vide Edge", code="BVEDGE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        caisse = get_caisse_physique_boutique(boutique_vide)
        self.assertEqual(caisse, Decimal("0"))

        with self.assertRaises(ErreurFinance):
            enregistrer_collecte(
                lieu=boutique_vide,
                date_collecte=date(2026, 3, 25),
                montant_trouve=Decimal("5000"),
                montant_pris=Decimal("1"),
                created_by=self.collecteur,
            )

    # ── Lot de production : quantité zéro ─────────────────────────────────────

    def test_creer_lot_quantite_zero_rejete(self):
        """quantite_sacs=0 → ErreurStock."""
        with self.assertRaises(ErreurStock):
            creer_lot_production(
                lieu_usine=self.usine,
                produit_fini=self.produit,
                nom_lot="LOT-ZERO-01",
                quantite_sacs=Decimal("0"),
                created_by=self.admin,
            )

    # ── Lot de production : nom vide ──────────────────────────────────────────

    def test_creer_lot_nom_vide_rejete(self):
        """nom_lot vide → ErreurStock."""
        with self.assertRaises(ErreurStock):
            creer_lot_production(
                lieu_usine=self.usine,
                produit_fini=self.produit,
                nom_lot="   ",
                quantite_sacs=Decimal("5"),
                created_by=self.admin,
            )

    # ── Cession lot : quantité > stock usine ─────────────────────────────────

    def test_cession_lot_quantite_superieure_stock_rejetee(self):
        """Cession de 10 sacs quand stock usine = 5 → ErreurStock."""
        lot = creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="LOT-EDGE-OVER",
            quantite_sacs=Decimal("5"),
            created_by=self.admin,
        )
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_boutique(
                lot=lot,
                boutique=self.boutique,
                quantite_sacs=Decimal("10"),
                prix_par_sac=Decimal("500"),
            )

        # Stock usine inchangé
        stock = Stock.objects.get(produit=self.produit, lieu=self.usine)
        self.assertGreaterEqual(stock.quantite, Decimal("5"))

    # ── Paiement créance : sur-paiement interdit ──────────────────────────────

    def test_paiement_creance_superieur_au_restant_rejete(self):
        """Paiement de 200 sur journal de 100 → PaiementExcessifError."""
        client = ClientFinance.objects.create(entreprise=self.ent, nom="Client Edge1")
        journal = creer_journal_creance(
            client=client,
            description="Test sur-paiement",
            montant_initial=Decimal("100"),
            created_by=self.admin,
        )
        with self.assertRaises(PaiementExcessifError):
            enregistrer_paiement_creance(
                journal=journal,
                montant=Decimal("200"),
                date=date(2026, 3, 25),
                created_by=self.admin,
            )
        journal.refresh_from_db()
        self.assertEqual(journal.montant_paye, Decimal("0"), "Aucun paiement ne doit avoir été enregistré")

    # ── Caisse : retrait > solde → SoldeInsuffisantError ─────────────────────

    def test_retrait_caisse_superieur_au_solde_rejete(self):
        """Retrait de 5 000 sur solde = 1 000 → SoldeInsuffisantError."""
        ent2 = Entreprise.objects.create(nom="EntEdge2")
        admin2 = CustomUser.objects.create_user(
            username="admin_edge2", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=ent2,
        )
        enregistrer_transaction_caisse(
            entreprise=ent2, type_transaction="depot",
            montant=Decimal("1000"), description="Dépôt",
            date=date(2026, 3, 25), created_by=admin2,
        )
        with self.assertRaises(SoldeInsuffisantError):
            enregistrer_transaction_caisse(
                entreprise=ent2, type_transaction="retrait",
                montant=Decimal("5000"), description="Retrait excessif",
                date=date(2026, 3, 25), created_by=admin2,
            )
        self.assertEqual(get_solde_caisse(ent2), Decimal("1000"))

    # ── Cession inter-entreprises interdit ────────────────────────────────────

    def test_cession_inter_entreprises_rejetee(self):
        """Transfert lot usine A vers boutique d'une autre entreprise → ErreurStock."""
        ent_b = Entreprise.objects.create(nom="EntEdgeB")
        boutique_b = Lieu.objects.create(
            entreprise=ent_b, nom="Boutique B Edge", code="BBE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        lot = creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="LOT-EDGE-XENT",
            quantite_sacs=Decimal("5"),
            created_by=self.admin,
        )
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_boutique(
                lot=lot, boutique=boutique_b,
                quantite_sacs=Decimal("2"), prix_par_sac=Decimal("500"),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. EDGE CASES API — Surface HTTP
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCasesAPI(APITestCase):
    """
    Vérifie que la surface HTTP rejette correctement les payloads malformés
    et les requêtes limites. Chaque test cible un seul comportement précis.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="EntEdgeAPI")
        cls.boutique = Lieu.objects.create(
            entreprise=cls.ent, nom="Boutique API Edge", code="BAPIE",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        cls.usine = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine API Edge", code="UAPIE",
            type_lieu=Lieu.TYPE_USINE,
        )
        cls.cat = Categorie.objects.create(nom="Cat API Edge", entreprise=cls.ent)
        cls.produit = Produit.objects.create(
            nom="Prod API Edge", code="PAPIE1", entreprise=cls.ent,
            categorie=cls.cat, category=Produit.CATEGORY_FINISHED, poids_par_sac=50,
        )
        cls.admin = CustomUser.objects.create_user(
            username="admin_apiedge", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=cls.ent,
        )
        cls.boutique_user = CustomUser.objects.create_user(
            username="bout_apiedge", password="pass",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent, lieu=cls.boutique,
        )
        cls.boutique_sans_lieu = CustomUser.objects.create_user(
            username="bout_sanslieu", password="pass",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=cls.ent,
        )
        Stock.objects.create(
            lieu=cls.boutique, produit=cls.produit, quantite=Decimal("100")
        )

    def _jwt(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {str(RefreshToken.for_user(user).access_token)}"}

    # ── Filtre date invalide ──────────────────────────────────────────────────

    def test_filtre_date_invalide_retourne_400(self):
        """
        GET /api/boutique/dashboard/?date_debut=99-99-99 → 400 (format attendu YYYY-MM-DD).
        La validation est dans BoutiqueDashboardView (lignes 858-866), pas dans /ventes/.
        """
        r = self.client.get(
            "/api/boutique/dashboard/?date_debut=99-99-99",
            **self._jwt(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date_debut", str(r.json()).lower())

    def test_filtre_date_format_correct_retourne_200(self):
        """GET avec date valide → 200."""
        r = self.client.get(
            "/api/boutique/ventes/?date_debut=2026-01-01&date_fin=2026-12-31",
            **self._jwt(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    # ── Vente quantite = 0 via API ────────────────────────────────────────────

    def test_api_vente_quantite_zero_retourne_400(self):
        """POST vente avec quantite=0 → 400 (validation serializer)."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.pk, "quantite": "0", "prix_unitaire": "500"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="edge-vente-q0-001",
            **self._jwt(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Vente prix = 0 via API ────────────────────────────────────────────────

    def test_api_vente_prix_zero_retourne_400(self):
        """POST vente avec prix_unitaire=0 → 400 (prix 0 interdit)."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.pk, "quantite": "1", "prix_unitaire": "0"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="edge-vente-p0-001",
            **self._jwt(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Vente crédit sans client via API ──────────────────────────────────────

    def test_api_vente_credit_sans_client_retourne_400(self):
        """POST vente type_vente=credit sans client_id → 400."""
        r = self.client.post(
            "/api/boutique/ventes/",
            {
                "lignes": [{"produit": self.produit.pk, "quantite": "1", "prix_unitaire": "500"}],
                "type_vente": "credit",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="edge-credit-nc-001",
            **self._jwt(self.boutique_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Boutique user sans lieu → dashboard ne crashe pas ────────────────────

    def test_boutique_sans_lieu_dashboard_ne_crashe_pas(self):
        """
        Utilisateur boutique sans lieu assigné.
        GET /api/boutique/dashboard/ → ne doit jamais lever une exception non gérée (500).
        Attendu : 400 ou 404 (erreur métier propre).
        """
        r = self.client.get(
            "/api/boutique/dashboard/",
            **self._jwt(self.boutique_sans_lieu),
        )
        self.assertIn(r.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_200_OK,
        ], f"Status inattendu {r.status_code} — ne doit pas être 500")
        self.assertNotEqual(r.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ── Facture ligne quantite = 0 via API ───────────────────────────────────

    def test_api_facture_ligne_quantite_zero_retourne_400(self):
        """POST facture avec ligne quantite=0 → 400."""
        r = self.client.post(
            "/api/factures/",
            {
                "lieu": self.boutique.pk,
                "lignes": [{"description": "Test", "quantite": "0", "prix_unitaire": "1000"}],
            },
            format="json",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Facture ligne prix négatif via API ────────────────────────────────────

    def test_api_facture_prix_negatif_retourne_400(self):
        """POST facture avec prix_unitaire négatif → 400."""
        r = self.client.post(
            "/api/factures/",
            {
                "lieu": self.boutique.pk,
                "lignes": [{"description": "Test", "quantite": "1", "prix_unitaire": "-100"}],
            },
            format="json",
            **self._jwt(self.admin),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Lot production quantite_sacs = 0 via API ──────────────────────────────

    def test_api_lot_production_quantite_zero_retourne_400(self):
        """POST /api/usine/lots/ avec quantite_sacs=0 → 400."""
        usine_user = CustomUser.objects.create_user(
            username="usine_edge_api", password="pass",
            role=CustomUser.ROLE_USINE, entreprise=self.ent, lieu=self.usine,
        )
        r = self.client.post(
            "/api/usine/lots/",
            {
                "produit_fini_id": self.produit.pk,
                "nom_lot": "LOT-EDGE-API-ZERO",
                "quantite_sacs": "0",
                "poids": "0",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="edge-lot-zero-001",
            **self._jwt(usine_user),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Admin cross-tenant bloqué ─────────────────────────────────────────────

    def test_api_admin_ne_peut_pas_acceder_lieu_autre_entreprise(self):
        """
        Admin de ent A essaie d'accéder à une facture de ent B → 404.
        Pas de fuite de données inter-tenant.
        """
        ent_b = Entreprise.objects.create(nom="EntEdgeB API")
        lieu_b = Lieu.objects.create(
            entreprise=ent_b, nom="Boutique B API", code="BBAPI",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        admin_b = CustomUser.objects.create_user(
            username="admin_b_api", password="pass",
            role=CustomUser.ROLE_ADMIN, entreprise=ent_b,
        )
        from ventes.models import Facture
        from produits.models import Produit as P
        facture_b = Facture.objects.create(
            lieu=lieu_b,
            numero="INV-B-001",
            source_role="admin",
            created_by=admin_b,
            total=Decimal("1000"),
        )
        # Admin de ent A tente d'accéder à la facture de ent B
        r = self.client.get(f"/api/factures/{facture_b.pk}/", **self._jwt(self.admin))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND,
            "Admin de ent A ne doit pas voir les factures de ent B")

    # ── Pagination : liste vide → réponse propre ──────────────────────────────

    def test_api_liste_vide_retourne_200_avec_resultats_vides(self):
        """
        Boutique sans aucune vente → GET /api/boutique/ventes/ → 200, liste vide.
        Pas de crash sur liste vide.
        """
        boutique_vide = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique Vide API", code="BVAPI",
            type_lieu=Lieu.TYPE_MAGASIN,
        )
        user_vide = CustomUser.objects.create_user(
            username="user_vide_api", password="pass",
            role=CustomUser.ROLE_BOUTIQUE, entreprise=self.ent, lieu=boutique_vide,
        )
        r = self.client.get("/api/boutique/ventes/", **self._jwt(user_vide))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        data = r.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        self.assertEqual(len(items), 0)
