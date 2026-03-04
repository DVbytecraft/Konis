"""
Tests unitaires — usine/services.py
Couvre : creer_lot_production(), transferer_lot_vers_boutique(), transferer_lot_vers_usine().
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from core.models import Entreprise, Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Produit
from usine.models import LotProduction, TransfertCession, TransfertInterUsine
from usine.services import (
    creer_lot_production,
    transferer_lot_vers_boutique,
    transferer_lot_vers_usine,
)


def _setup_base():
    """Crée les objets de base pour les tests usine."""
    ent = Entreprise.objects.create(nom="KONIS Usine Test")
    usine = Lieu.objects.create(
        entreprise=ent, nom="Usine Alpha", code="UAL", type_lieu=Lieu.TYPE_USINE
    )
    usine2 = Lieu.objects.create(
        entreprise=ent, nom="Usine Beta", code="UBE", type_lieu=Lieu.TYPE_USINE
    )
    boutique = Lieu.objects.create(
        entreprise=ent, nom="Boutique Alpha", code="BAL", type_lieu=Lieu.TYPE_MAGASIN
    )
    produit = Produit.objects.create(nom="Provende 50kg", code="PRV50", unite="sac", entreprise=ent)
    return ent, usine, usine2, boutique, produit


# ─── Tests creer_lot_production ───────────────────────────────────────────────

class TestCreerLotProduction(APITestCase):
    """Tests du service creer_lot_production()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.usine, cls.usine2, cls.boutique, cls.produit = _setup_base()

    def test_lot_cree_en_base(self):
        """Un lot valide est créé en base de données."""
        lot = creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="LOT-001",
            quantite_sacs=Decimal("100"),
        )
        self.assertIsNotNone(lot.pk)
        self.assertEqual(lot.nom_lot, "LOT-001")
        self.assertEqual(lot.lieu_usine, self.usine)
        self.assertEqual(lot.produit_fini, self.produit)
        self.assertEqual(lot.quantite_sacs, Decimal("100"))

    def test_stock_credite_apres_creation_lot(self):
        """Le stock du produit fini à l'usine est crédité après création du lot."""
        creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="LOT-002",
            quantite_sacs=Decimal("50"),
        )
        stock = Stock.objects.get(produit=self.produit, lieu=self.usine)
        # Le stock inclut tous les lots créés dans ce test, donc on vérifie >= 50
        self.assertGreaterEqual(stock.quantite, Decimal("50"))

    def test_stock_cree_si_absent(self):
        """Si aucun stock n'existe pour ce produit à cette usine, il est créé."""
        produit_neuf = Produit.objects.create(nom="Neuf Lot", code="NLT", unite="sac", entreprise=self.ent)
        self.assertFalse(Stock.objects.filter(produit=produit_neuf, lieu=self.usine2).exists())
        creer_lot_production(
            lieu_usine=self.usine2,
            produit_fini=produit_neuf,
            nom_lot="LOT-003",
            quantite_sacs=Decimal("20"),
        )
        self.assertTrue(Stock.objects.filter(produit=produit_neuf, lieu=self.usine2).exists())

    def test_stock_incremente_si_existant(self):
        """Si un stock existe déjà, il est incrémenté (pas écrasé)."""
        produit_cumul = Produit.objects.create(nom="Cumul", code="CUMU", unite="sac", entreprise=self.ent)
        creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=produit_cumul,
            nom_lot="LOT-CUM1",
            quantite_sacs=Decimal("30"),
        )
        creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=produit_cumul,
            nom_lot="LOT-CUM2",
            quantite_sacs=Decimal("20"),
        )
        stock = Stock.objects.get(produit=produit_cumul, lieu=self.usine)
        self.assertEqual(stock.quantite, Decimal("50"))

    def test_lieu_non_usine_leve_erreur(self):
        """ErreurStock si le lieu n'est pas une usine."""
        with self.assertRaises(ErreurStock) as ctx:
            creer_lot_production(
                lieu_usine=self.boutique,
                produit_fini=self.produit,
                nom_lot="LOT-ERR",
                quantite_sacs=Decimal("10"),
            )
        self.assertIn("usine", str(ctx.exception))

    def test_quantite_zero_leve_erreur(self):
        """ErreurStock si quantite_sacs = 0."""
        with self.assertRaises(ErreurStock):
            creer_lot_production(
                lieu_usine=self.usine,
                produit_fini=self.produit,
                nom_lot="LOT-ZERO",
                quantite_sacs=Decimal("0"),
            )

    def test_quantite_negative_leve_erreur(self):
        """ErreurStock si quantite_sacs < 0."""
        with self.assertRaises(ErreurStock):
            creer_lot_production(
                lieu_usine=self.usine,
                produit_fini=self.produit,
                nom_lot="LOT-NEG",
                quantite_sacs=Decimal("-10"),
            )

    def test_poids_negatif_leve_erreur(self):
        """ErreurStock si poids < 0."""
        with self.assertRaises(ErreurStock):
            creer_lot_production(
                lieu_usine=self.usine,
                produit_fini=self.produit,
                nom_lot="LOT-PNEG",
                quantite_sacs=Decimal("10"),
                poids=Decimal("-5"),
            )

    def test_nom_lot_vide_leve_erreur(self):
        """ErreurStock si nom_lot est vide ou espace."""
        with self.assertRaises(ErreurStock):
            creer_lot_production(
                lieu_usine=self.usine,
                produit_fini=self.produit,
                nom_lot="   ",
                quantite_sacs=Decimal("10"),
            )

    def test_nom_lot_trimme(self):
        """Le nom de lot est nettoyé des espaces."""
        lot = creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="  LOT-TRIM  ",
            quantite_sacs=Decimal("5"),
        )
        self.assertEqual(lot.nom_lot, "LOT-TRIM")

    def test_lot_avec_poids_et_unite_tonnes(self):
        """Un lot avec poids en tonnes est créé correctement."""
        lot = creer_lot_production(
            lieu_usine=self.usine,
            produit_fini=self.produit,
            nom_lot="LOT-TONNE",
            quantite_sacs=Decimal("200"),
            poids=Decimal("10"),
            unite_poids="tonnes",
        )
        self.assertEqual(lot.poids, Decimal("10"))
        self.assertEqual(lot.unite_poids, "tonnes")


# ─── Tests transferer_lot_vers_boutique ──────────────────────────────────────

class TestTransfererLotVersBoutique(APITestCase):
    """Tests du service transferer_lot_vers_boutique()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.usine, cls.usine2, cls.boutique, cls.produit = _setup_base()
        # Créer un lot de départ avec stock à l'usine
        cls.lot = creer_lot_production(
            lieu_usine=cls.usine,
            produit_fini=cls.produit,
            nom_lot="LOT-CESSION-BASE",
            quantite_sacs=Decimal("200"),
            poids=Decimal("10000"),
        )

    def test_cession_cree_objet_transfert_cession(self):
        """Une cession valide crée un TransfertCession en base."""
        cession = transferer_lot_vers_boutique(
            lot=self.lot,
            boutique=self.boutique,
            quantite_sacs=Decimal("20"),
            prix_par_sac=Decimal("5000"),
        )
        self.assertIsNotNone(cession.pk)
        self.assertIsInstance(cession, TransfertCession)
        self.assertEqual(cession.lot, self.lot)
        self.assertEqual(cession.boutique, self.boutique)

    def test_stock_usine_diminue(self):
        """Le stock de l'usine diminue après une cession."""
        stock_avant = Stock.objects.get(produit=self.produit, lieu=self.usine).quantite
        transferer_lot_vers_boutique(
            lot=self.lot,
            boutique=self.boutique,
            quantite_sacs=Decimal("10"),
            prix_par_sac=Decimal("4500"),
        )
        stock_apres = Stock.objects.get(produit=self.produit, lieu=self.usine).quantite
        self.assertEqual(stock_avant - stock_apres, Decimal("10"))

    def test_stock_boutique_augmente(self):
        """Le stock de la boutique augmente après une cession."""
        quantite_cedee = Decimal("15")
        transferer_lot_vers_boutique(
            lot=self.lot,
            boutique=self.boutique,
            quantite_sacs=quantite_cedee,
            prix_par_sac=Decimal("5500"),
        )
        stock_boutique = Stock.objects.filter(produit=self.produit, lieu=self.boutique).first()
        self.assertIsNotNone(stock_boutique)
        self.assertGreaterEqual(stock_boutique.quantite, quantite_cedee)

    def test_cession_avec_poids_total(self):
        """Le poids total est enregistré correctement dans la cession."""
        cession = transferer_lot_vers_boutique(
            lot=self.lot,
            boutique=self.boutique,
            quantite_sacs=Decimal("5"),
            poids_total=Decimal("250"),
            prix_par_sac=Decimal("6000"),
        )
        self.assertEqual(cession.poids_total, Decimal("250"))

    def test_destination_non_boutique_leve_erreur(self):
        """ErreurStock si la destination n'est pas un magasin."""
        with self.assertRaises(ErreurStock) as ctx:
            transferer_lot_vers_boutique(
                lot=self.lot,
                boutique=self.usine2,
                quantite_sacs=Decimal("5"),
                prix_par_sac=Decimal("1000"),
            )
        self.assertIn("boutique", str(ctx.exception))

    def test_quantite_zero_leve_erreur(self):
        """ErreurStock si quantite_sacs = 0."""
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_boutique(
                lot=self.lot,
                boutique=self.boutique,
                quantite_sacs=Decimal("0"),
                prix_par_sac=Decimal("5000"),
            )

    def test_prix_par_sac_negatif_leve_erreur(self):
        """ErreurStock si prix_par_sac < 0."""
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_boutique(
                lot=self.lot,
                boutique=self.boutique,
                quantite_sacs=Decimal("5"),
                prix_par_sac=Decimal("-1"),
            )

    def test_stock_insuffisant_leve_erreur(self):
        """ErreurStock si la quantite cédée > stock disponible."""
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_boutique(
                lot=self.lot,
                boutique=self.boutique,
                quantite_sacs=Decimal("99999"),
                prix_par_sac=Decimal("5000"),
            )

    def test_prix_par_sac_zero_accepte(self):
        """prix_par_sac = 0 est autorisé."""
        cession = transferer_lot_vers_boutique(
            lot=self.lot,
            boutique=self.boutique,
            quantite_sacs=Decimal("1"),
            prix_par_sac=Decimal("0"),
        )
        self.assertEqual(cession.prix_par_sac, Decimal("0"))

    def test_cession_lie_au_transfert_inventaire(self):
        """La cession est liée à un objet Transfert inventaire."""
        cession = transferer_lot_vers_boutique(
            lot=self.lot,
            boutique=self.boutique,
            quantite_sacs=Decimal("2"),
            prix_par_sac=Decimal("4000"),
        )
        self.assertIsNotNone(cession.transfert)


# ─── Tests transferer_lot_vers_usine ─────────────────────────────────────────

class TestTransfererLotVersUsine(APITestCase):
    """Tests du service transferer_lot_vers_usine()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.usine, cls.usine2, cls.boutique, cls.produit = _setup_base()
        cls.lot = creer_lot_production(
            lieu_usine=cls.usine,
            produit_fini=cls.produit,
            nom_lot="LOT-INTER-BASE",
            quantite_sacs=Decimal("150"),
        )

    def test_transfert_inter_usine_cree_objet(self):
        """Un transfert inter-usine valide crée un TransfertInterUsine."""
        inter = transferer_lot_vers_usine(
            lot=self.lot,
            usine_destination=self.usine2,
            quantite_sacs=Decimal("30"),
            prix_par_sac=Decimal("3000"),
        )
        self.assertIsNotNone(inter.pk)
        self.assertIsInstance(inter, TransfertInterUsine)
        self.assertEqual(inter.lot, self.lot)
        self.assertEqual(inter.usine_destination, self.usine2)

    def test_stock_usine_source_diminue(self):
        """Le stock de l'usine source diminue après un transfert inter-usine."""
        stock_avant = Stock.objects.get(produit=self.produit, lieu=self.usine).quantite
        transferer_lot_vers_usine(
            lot=self.lot,
            usine_destination=self.usine2,
            quantite_sacs=Decimal("20"),
        )
        stock_apres = Stock.objects.get(produit=self.produit, lieu=self.usine).quantite
        self.assertEqual(stock_avant - stock_apres, Decimal("20"))

    def test_stock_usine_destination_augmente(self):
        """Le stock de l'usine de destination augmente."""
        quantite = Decimal("25")
        transferer_lot_vers_usine(
            lot=self.lot,
            usine_destination=self.usine2,
            quantite_sacs=quantite,
        )
        stock = Stock.objects.filter(produit=self.produit, lieu=self.usine2).first()
        self.assertIsNotNone(stock)
        self.assertGreaterEqual(stock.quantite, quantite)

    def test_destination_non_usine_leve_erreur(self):
        """ErreurStock si la destination n'est pas une usine."""
        with self.assertRaises(ErreurStock) as ctx:
            transferer_lot_vers_usine(
                lot=self.lot,
                usine_destination=self.boutique,
                quantite_sacs=Decimal("5"),
            )
        self.assertIn("usine", str(ctx.exception))

    def test_meme_usine_source_destination_leve_erreur(self):
        """ErreurStock si l'usine source et destination sont identiques."""
        with self.assertRaises(ErreurStock) as ctx:
            transferer_lot_vers_usine(
                lot=self.lot,
                usine_destination=self.usine,
                quantite_sacs=Decimal("5"),
            )
        self.assertIn("differentes", str(ctx.exception))

    def test_quantite_zero_leve_erreur(self):
        """ErreurStock si quantite_sacs = 0."""
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_usine(
                lot=self.lot,
                usine_destination=self.usine2,
                quantite_sacs=Decimal("0"),
            )

    def test_stock_insuffisant_leve_erreur(self):
        """ErreurStock si quantite > stock disponible à l'usine source."""
        with self.assertRaises(ErreurStock):
            transferer_lot_vers_usine(
                lot=self.lot,
                usine_destination=self.usine2,
                quantite_sacs=Decimal("99999"),
            )

    def test_transfert_avec_notes(self):
        """Les notes sont correctement enregistrées."""
        inter = transferer_lot_vers_usine(
            lot=self.lot,
            usine_destination=self.usine2,
            quantite_sacs=Decimal("5"),
            notes="Transfert pour commande urgente",
        )
        self.assertEqual(inter.notes, "Transfert pour commande urgente")

    def test_transfert_lie_au_transfert_inventaire(self):
        """Le TransfertInterUsine est lié à un Transfert inventaire."""
        inter = transferer_lot_vers_usine(
            lot=self.lot,
            usine_destination=self.usine2,
            quantite_sacs=Decimal("3"),
        )
        self.assertIsNotNone(inter.transfert)
