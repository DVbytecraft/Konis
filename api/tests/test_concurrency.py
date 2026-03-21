"""
Tests de concurrence : vente simultanée, double paiement, double conversion.
"""
from decimal import Decimal
import threading
from datetime import date

from django.test import TransactionTestCase
from django.db import close_old_connections

from core.models import Entreprise, Lieu, CustomUser
from inventaire.models import Stock
from inventaire.services import ErreurStock, convertir_sac_en_kg
from produits.models import Produit
from finance.models import ClientFinance
from finance.services import creer_journal_creance, enregistrer_paiement_creance, PaiementExcessifError
from ventes.services import vente_boutique


class ConcurrencyTests(TransactionTestCase):

    def setUp(self):
        self.ent = Entreprise.objects.create(nom="KONIS Concurrency")
        self.boutique = Lieu.objects.create(
            entreprise=self.ent, nom="Boutique C", code="BTC", type_lieu=Lieu.TYPE_MAGASIN
        )
        self.user = CustomUser.objects.create_user(
            username="user_c", password="pass", role=CustomUser.ROLE_BOUTIQUE,
            entreprise=self.ent, lieu=self.boutique,
        )

    def test_vente_simultanee_meme_stock(self):
        produit = Produit.objects.create(nom="Riz kg", code="RKG2", unite="kg", entreprise=self.ent)
        Stock.objects.create(produit=produit, lieu=self.boutique, quantite=Decimal("10"))

        results = [None, None]

        def _worker(idx):
            close_old_connections()
            try:
                vente_boutique(self.boutique, [(produit, Decimal("10"), Decimal("100"))])
                results[idx] = "ok"
            except Exception as e:
                results[idx] = e
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_worker, args=(0,))
        t2 = threading.Thread(target=_worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(sum(isinstance(r, Exception) for r in results), 1)
        self.assertTrue(any(isinstance(r, ErreurStock) for r in results))

        stock = Stock.objects.get(produit=produit, lieu=self.boutique)
        self.assertGreaterEqual(stock.quantite, Decimal("0"))

    def test_double_paiement_creance(self):
        client = ClientFinance.objects.create(entreprise=self.ent, nom="Client C")
        journal = creer_journal_creance(
            client=client,
            description="Test",
            montant_initial=Decimal("100"),
            created_by=self.user,
        )

        results = [None, None]

        def _worker(idx):
            close_old_connections()
            try:
                enregistrer_paiement_creance(
                    journal=journal,
                    montant=Decimal("60"),
                    date=date(2026, 3, 21),
                    created_by=self.user,
                )
                results[idx] = "ok"
            except Exception as e:
                results[idx] = e
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_worker, args=(0,))
        t2 = threading.Thread(target=_worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertEqual(results.count("ok"), 1)
        self.assertTrue(any(isinstance(r, PaiementExcessifError) for r in results))

        journal.refresh_from_db()
        self.assertEqual(journal.montant_paye, Decimal("60"))
        self.assertEqual(journal.montant_restant, Decimal("40"))

    def test_double_conversion_sac_kg(self):
        produit = Produit.objects.create(
            nom="Maïs sac", code="MSAC", unite="sac", entreprise=self.ent,
            poids_par_sac=Decimal("50.000"),
        )
        stock = Stock.objects.create(
            produit=produit, lieu=self.boutique, quantite=Decimal("2"), quantite_kg=Decimal("0")
        )

        results = [None, None]

        def _worker(idx):
            close_old_connections()
            try:
                convertir_sac_en_kg(stock=stock, nombre_sacs=2, updated_by=self.user)
                results[idx] = "ok"
            except Exception as e:
                results[idx] = e
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_worker, args=(0,))
        t2 = threading.Thread(target=_worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertEqual(results.count("ok"), 1)
        self.assertTrue(any(isinstance(r, ErreurStock) for r in results))

        stock.refresh_from_db()
        self.assertEqual(stock.quantite, Decimal("0"))
        self.assertEqual(stock.quantite_kg, Decimal("100"))
