"""
Tests unitaires — inventaire/services.py
Couvre : enregistrer_achat_usine(), transfert_usine_vers_boutique(),
         transfert_entre_usines(), _executer_transfert() (cas d'erreur).
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from core.models import Entreprise, Lieu
from inventaire.models import AchatUsine, MouvementStock, Stock, Transfert
from inventaire.services import (
    ErreurStock,
    enregistrer_achat_usine,
    transfert_entre_usines,
    transfert_usine_vers_boutique,
)
from produits.models import Produit


def _setup_base():
    """Crée les objets de base pour les tests inventaire."""
    ent = Entreprise.objects.create(nom="KONIS Inv Test")
    usine = Lieu.objects.create(
        entreprise=ent, nom="Usine Nord", code="USN", type_lieu=Lieu.TYPE_USINE
    )
    usine2 = Lieu.objects.create(
        entreprise=ent, nom="Usine Sud", code="USS", type_lieu=Lieu.TYPE_USINE
    )
    boutique = Lieu.objects.create(
        entreprise=ent, nom="Boutique Inv", code="BIV", type_lieu=Lieu.TYPE_MAGASIN
    )
    produit_a = Produit.objects.create(nom="Maïs 50kg", code="MA50", unite="sac", entreprise=ent)
    produit_b = Produit.objects.create(nom="Mil kg", code="MILKG", unite="kg", entreprise=ent)
    return ent, usine, usine2, boutique, produit_a, produit_b


# ─── Tests enregistrer_achat_usine ────────────────────────────────────────────

class TestEnregistrerAchatUsine(APITestCase):
    """Tests du service enregistrer_achat_usine()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.usine, cls.usine2, cls.boutique, cls.produit_a, _ = _setup_base()

    def test_achat_enregistre_en_base(self):
        """Un achat valide crée un AchatUsine en base de données."""
        achat = enregistrer_achat_usine(
            lieu=self.usine,
            produit_nom="Maïs local",
            quantite=Decimal("100"),
            unite="sacs",
            prix_unitaire=Decimal("2500"),
        )
        self.assertIsNotNone(achat.pk)
        self.assertEqual(achat.lieu, self.usine)
        self.assertEqual(achat.produit_nom, "Maïs local")
        self.assertEqual(achat.quantite, Decimal("100"))

    def test_prix_total_calcule_correctement(self):
        """prix_total = quantite × prix_unitaire."""
        achat = enregistrer_achat_usine(
            lieu=self.usine,
            produit_nom="Soja",
            quantite=Decimal("50"),
            unite="kg",
            prix_unitaire=Decimal("1000"),
        )
        self.assertEqual(achat.prix_total, Decimal("50") * Decimal("1000"))

    def test_achat_sur_boutique_leve_erreur(self):
        """Un achat sur un lieu non-usine lève ErreurStock."""
        with self.assertRaises(ErreurStock) as ctx:
            enregistrer_achat_usine(
                lieu=self.boutique,
                produit_nom="Test",
                quantite=Decimal("10"),
                unite="sacs",
            )
        self.assertIn("usine", str(ctx.exception))

    def test_produit_nom_vide_leve_erreur(self):
        """Un nom de produit vide ou espace est refusé."""
        with self.assertRaises(ErreurStock):
            enregistrer_achat_usine(
                lieu=self.usine,
                produit_nom="   ",
                quantite=Decimal("10"),
                unite="sacs",
            )

    def test_quantite_zero_leve_erreur(self):
        """Quantité <= 0 lève ErreurStock."""
        with self.assertRaises(ErreurStock):
            enregistrer_achat_usine(
                lieu=self.usine,
                produit_nom="Maïs",
                quantite=Decimal("0"),
                unite="sacs",
            )

    def test_prix_unitaire_negatif_leve_erreur(self):
        """Prix unitaire < 0 lève ErreurStock."""
        with self.assertRaises(ErreurStock):
            enregistrer_achat_usine(
                lieu=self.usine,
                produit_nom="Maïs",
                quantite=Decimal("10"),
                unite="sacs",
                prix_unitaire=Decimal("-1"),
            )

    def test_prix_unitaire_zero_accepte(self):
        """Prix unitaire = 0 est autorisé (don/collecte sans coût)."""
        achat = enregistrer_achat_usine(
            lieu=self.usine,
            produit_nom="Maïs gratuit",
            quantite=Decimal("5"),
            unite="sacs",
            prix_unitaire=Decimal("0"),
        )
        self.assertEqual(achat.prix_unitaire, Decimal("0"))

    def test_notes_enregistrees(self):
        """Les notes sont correctement enregistrées."""
        achat = enregistrer_achat_usine(
            lieu=self.usine,
            produit_nom="Mil",
            quantite=Decimal("20"),
            unite="sacs",
            notes="Achat fournisseur X",
        )
        self.assertEqual(achat.notes, "Achat fournisseur X")


# ─── Tests transfert_usine_vers_boutique ─────────────────────────────────────

class TestTransfertUsineVersBoutique(APITestCase):
    """Tests du service transfert_usine_vers_boutique()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.usine, cls.usine2, cls.boutique, cls.produit_a, cls.produit_b = _setup_base()
        Stock.objects.create(produit=cls.produit_a, lieu=cls.usine, quantite=Decimal("200"))
        Stock.objects.create(produit=cls.produit_b, lieu=cls.usine, quantite=Decimal("500"))

    def test_transfert_cree_objet_transfert(self):
        """Un transfert valide crée un objet Transfert en base."""
        t = transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.boutique,
            lignes=[(self.produit_a, Decimal("10"))],
        )
        self.assertIsNotNone(t.pk)
        self.assertEqual(t.from_lieu, self.usine)
        self.assertEqual(t.to_lieu, self.boutique)

    def test_transfert_cree_mouvement_stock(self):
        """Un transfert crée une ligne MouvementStock par produit."""
        t = transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.boutique,
            lignes=[(self.produit_a, Decimal("5")), (self.produit_b, Decimal("20"))],
        )
        self.assertEqual(t.mouvements.count(), 2)

    def test_stock_usine_diminue(self):
        """Le stock source diminue de la quantité transférée."""
        stock_avant = Stock.objects.get(produit=self.produit_a, lieu=self.usine).quantite
        transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.boutique,
            lignes=[(self.produit_a, Decimal("30"))],
        )
        stock_apres = Stock.objects.get(produit=self.produit_a, lieu=self.usine).quantite
        self.assertEqual(stock_avant - stock_apres, Decimal("30"))

    def test_stock_boutique_augmente(self):
        """Le stock destination augmente de la quantité transférée."""
        transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.boutique,
            lignes=[(self.produit_b, Decimal("50"))],
        )
        stock_boutique = Stock.objects.get(produit=self.produit_b, lieu=self.boutique).quantite
        self.assertEqual(stock_boutique, Decimal("50"))

    def test_stock_boutique_cree_si_absent(self):
        """Si la boutique n'a pas encore le produit, un Stock est créé."""
        produit_neuf = Produit.objects.create(nom="Neuf", code="NEF", unite="kg", entreprise=self.ent)
        Stock.objects.create(produit=produit_neuf, lieu=self.usine, quantite=Decimal("100"))
        self.assertFalse(Stock.objects.filter(produit=produit_neuf, lieu=self.boutique).exists())
        transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.boutique,
            lignes=[(produit_neuf, Decimal("10"))],
        )
        self.assertTrue(Stock.objects.filter(produit=produit_neuf, lieu=self.boutique).exists())

    def test_stock_insuffisant_leve_erreur(self):
        """ErreurStock si quantité demandée > stock disponible."""
        with self.assertRaises(ErreurStock) as ctx:
            transfert_usine_vers_boutique(
                from_lieu=self.usine,
                to_lieu=self.boutique,
                lignes=[(self.produit_a, Decimal("9999"))],
            )
        self.assertIn("insuffisant", str(ctx.exception))

    def test_stock_absent_leve_erreur(self):
        """ErreurStock si le produit n'existe pas en stock à l'usine."""
        produit_absent = Produit.objects.create(nom="Absent", code="ABS2", unite="kg", entreprise=self.ent)
        with self.assertRaises(ErreurStock):
            transfert_usine_vers_boutique(
                from_lieu=self.usine,
                to_lieu=self.boutique,
                lignes=[(produit_absent, Decimal("1"))],
            )

    def test_quantite_zero_leve_erreur(self):
        """ErreurStock si quantité = 0."""
        with self.assertRaises(ErreurStock):
            transfert_usine_vers_boutique(
                from_lieu=self.usine,
                to_lieu=self.boutique,
                lignes=[(self.produit_a, Decimal("0"))],
            )

    def test_origine_non_usine_leve_erreur(self):
        """ErreurStock si le lieu d'origine n'est pas une usine."""
        with self.assertRaises(ErreurStock) as ctx:
            transfert_usine_vers_boutique(
                from_lieu=self.boutique,
                to_lieu=self.boutique,
                lignes=[(self.produit_a, Decimal("1"))],
            )
        self.assertIn("usine", str(ctx.exception))

    def test_destination_non_magasin_leve_erreur(self):
        """ErreurStock si la destination n'est pas un magasin."""
        with self.assertRaises(ErreurStock) as ctx:
            transfert_usine_vers_boutique(
                from_lieu=self.usine,
                to_lieu=self.usine2,
                lignes=[(self.produit_a, Decimal("1"))],
            )
        self.assertIn("magasin", str(ctx.exception))

    def test_meme_lieu_origine_destination_leve_erreur(self):
        """ErreurStock si origine == destination."""
        with self.assertRaises(ErreurStock) as ctx:
            transfert_usine_vers_boutique(
                from_lieu=self.usine,
                to_lieu=self.usine,
                lignes=[(self.produit_a, Decimal("1"))],
            )
        # Le service valide d'abord que la destination est un magasin
        self.assertTrue(len(str(ctx.exception)) > 0)

    def test_transfert_avec_prix_unitaire(self):
        """Le prix unitaire est enregistré dans le MouvementStock."""
        t = transfert_usine_vers_boutique(
            from_lieu=self.usine,
            to_lieu=self.boutique,
            lignes=[(self.produit_a, Decimal("10"), Decimal("2500"))],
        )
        mouvement = t.mouvements.first()
        self.assertEqual(mouvement.unit_price, Decimal("2500"))

    def test_transfert_multi_produits_atomique(self):
        """Si une ligne échoue, aucun mouvement n'est appliqué (atomicité)."""
        produit_absent2 = Produit.objects.create(nom="Absent2", code="AB2", unite="kg", entreprise=self.ent)
        stock_avant = Stock.objects.get(produit=self.produit_a, lieu=self.usine).quantite
        with self.assertRaises(ErreurStock):
            transfert_usine_vers_boutique(
                from_lieu=self.usine,
                to_lieu=self.boutique,
                lignes=[
                    (self.produit_a, Decimal("10")),
                    (produit_absent2, Decimal("1")),  # Cette ligne échoue
                ],
            )
        # Le stock de produit_a ne doit pas avoir changé
        stock_apres = Stock.objects.get(produit=self.produit_a, lieu=self.usine).quantite
        self.assertEqual(stock_avant, stock_apres)


# ─── Tests transfert_entre_usines ─────────────────────────────────────────────

class TestTransfertEntreUsines(APITestCase):
    """Tests du service transfert_entre_usines()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.usine, cls.usine2, cls.boutique, cls.produit_a, cls.produit_b = _setup_base()
        Stock.objects.create(produit=cls.produit_a, lieu=cls.usine, quantite=Decimal("300"))
        Stock.objects.create(produit=cls.produit_b, lieu=cls.usine, quantite=Decimal("100"))

    def test_transfert_inter_usine_cree_objet(self):
        """Un transfert inter-usine valide crée un Transfert en base."""
        t = transfert_entre_usines(
            from_lieu=self.usine,
            to_lieu=self.usine2,
            lignes=[(self.produit_a, Decimal("50"))],
        )
        self.assertIsNotNone(t.pk)
        self.assertEqual(t.from_lieu, self.usine)
        self.assertEqual(t.to_lieu, self.usine2)

    def test_stock_source_diminue(self):
        """Le stock de l'usine source diminue."""
        stock_avant = Stock.objects.get(produit=self.produit_a, lieu=self.usine).quantite
        transfert_entre_usines(
            from_lieu=self.usine,
            to_lieu=self.usine2,
            lignes=[(self.produit_a, Decimal("40"))],
        )
        stock_apres = Stock.objects.get(produit=self.produit_a, lieu=self.usine).quantite
        self.assertEqual(stock_avant - stock_apres, Decimal("40"))

    def test_stock_destination_augmente(self):
        """Le stock de l'usine de destination augmente."""
        transfert_entre_usines(
            from_lieu=self.usine,
            to_lieu=self.usine2,
            lignes=[(self.produit_b, Decimal("30"))],
        )
        stock_usine2 = Stock.objects.get(produit=self.produit_b, lieu=self.usine2).quantite
        self.assertEqual(stock_usine2, Decimal("30"))

    def test_destination_non_usine_leve_erreur(self):
        """ErreurStock si la destination est un magasin."""
        with self.assertRaises(ErreurStock) as ctx:
            transfert_entre_usines(
                from_lieu=self.usine,
                to_lieu=self.boutique,
                lignes=[(self.produit_a, Decimal("1"))],
            )
        self.assertIn("usine", str(ctx.exception))

    def test_stock_insuffisant_leve_erreur(self):
        """ErreurStock si quantité > stock disponible."""
        with self.assertRaises(ErreurStock):
            transfert_entre_usines(
                from_lieu=self.usine,
                to_lieu=self.usine2,
                lignes=[(self.produit_a, Decimal("99999"))],
            )

    def test_meme_usine_origine_destination_leve_erreur(self):
        """ErreurStock si les deux usines sont identiques."""
        with self.assertRaises(ErreurStock):
            transfert_entre_usines(
                from_lieu=self.usine,
                to_lieu=self.usine,
                lignes=[(self.produit_a, Decimal("1"))],
            )

    def test_mouvement_enregistre_correctement(self):
        """MouvementStock créé avec les bonnes valeurs."""
        t = transfert_entre_usines(
            from_lieu=self.usine,
            to_lieu=self.usine2,
            lignes=[(self.produit_a, Decimal("20"), Decimal("3000"))],
        )
        mvt = t.mouvements.first()
        self.assertEqual(mvt.produit, self.produit_a)
        self.assertEqual(mvt.quantite, Decimal("20"))
        self.assertEqual(mvt.unit_price, Decimal("3000"))
