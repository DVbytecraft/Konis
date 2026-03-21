"""
Tests unitaires — ventes/services.py
Couvre : vente_boutique(), vente_mouture_seule(), generer_numero_ticket(), montant_total.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from core.models import Entreprise, Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Produit
from ventes.models import Ticket
from ventes.services import generer_numero_ticket, vente_boutique, vente_mouture_seule


def _setup_base():
    """Crée les objets de base pour les tests ventes."""
    ent = Entreprise.objects.create(nom="KONIS Test")
    boutique = Lieu.objects.create(
        entreprise=ent, nom="Boutique Test", code="TEST", type_lieu=Lieu.TYPE_MAGASIN
    )
    usine = Lieu.objects.create(
        entreprise=ent, nom="Usine Test", code="USN", type_lieu=Lieu.TYPE_USINE,
        mouture_enabled=True,
    )
    produit_kg = Produit.objects.create(nom="Maïs kg", code="MKG", unite="kg", entreprise=ent)
    produit_sac = Produit.objects.create(
        nom="Mil sac", code="MSC", unite="sac", entreprise=ent,
        poids_par_sac=Decimal("50.000"),  # 1 sac = 50 kg
    )
    return ent, boutique, usine, produit_kg, produit_sac


class TestVenteBoutique(APITestCase):
    """Tests du service vente_boutique()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.boutique, cls.usine, cls.produit_kg, cls.produit_sac = _setup_base()
        Stock.objects.create(produit=cls.produit_kg, lieu=cls.boutique, quantite=Decimal("100"))
        Stock.objects.create(produit=cls.produit_sac, lieu=cls.boutique, quantite=Decimal("20"))

    def test_vente_simple_cree_ticket_et_ligne(self):
        """Une vente valide crée un Ticket et une LigneVente."""
        ticket, _ = vente_boutique(
            self.boutique,
            [(self.produit_kg, Decimal("10"), Decimal("500"))],
        )
        self.assertIsNotNone(ticket.pk)
        self.assertEqual(ticket.lieu, self.boutique)
        self.assertEqual(ticket.lignes.count(), 1)

    def test_montant_total_calcule_correctement(self):
        """montant_total = somme(quantite × prix_unitaire)."""
        ticket, _ = vente_boutique(
            self.boutique,
            [
                (self.produit_kg, Decimal("10"), Decimal("500")),
                (self.produit_sac, Decimal("2"), Decimal("1000")),
            ],
        )
        attendu = Decimal("10") * Decimal("500") + Decimal("2") * Decimal("1000")
        self.assertEqual(ticket.montant_total, attendu)

    def test_stock_diminue_apres_vente(self):
        """Le stock est débité après la vente."""
        stock_avant = Stock.objects.get(produit=self.produit_kg, lieu=self.boutique).quantite
        vente_boutique(self.boutique, [(self.produit_kg, Decimal("5"), Decimal("200"))])
        stock_apres = Stock.objects.get(produit=self.produit_kg, lieu=self.boutique).quantite
        self.assertEqual(stock_avant - stock_apres, Decimal("5"))

    def test_vente_kg_utilise_quantite_kg_si_disponible(self):
        """Si quantite_kg est renseigné, la vente en kg débite quantite_kg."""
        produit_kg2 = Produit.objects.create(
            nom="Riz kg", code="RKG", unite="kg", entreprise=self.ent
        )
        Stock.objects.create(
            produit=produit_kg2, lieu=self.boutique,
            quantite=Decimal("0"), quantite_kg=Decimal("20"),
        )
        vente_boutique(self.boutique, [(produit_kg2, Decimal("5"), Decimal("300"))])
        stock_apres = Stock.objects.get(produit=produit_kg2, lieu=self.boutique)
        self.assertEqual(stock_apres.quantite_kg, Decimal("15"))
        self.assertEqual(stock_apres.quantite, Decimal("0"))

    def test_vente_mixte_sac_kg_conversion_auto(self):
        """
        Cas critique :
        5 sacs (50kg) -> 250kg + 50kg direct
        vente 270kg -> 0 sac, 30kg restant
        """
        produit_mixte = Produit.objects.create(
            nom="Maïs mixte", code="MMX", unite="sac",
            entreprise=self.ent, poids_par_sac=Decimal("50.000"),
        )
        Stock.objects.create(
            produit=produit_mixte, lieu=self.boutique,
            quantite=Decimal("5"), quantite_kg=Decimal("50"),
        )
        vente_boutique(self.boutique, [(produit_mixte, Decimal("270"), Decimal("200"), "kg")])
        stock_apres = Stock.objects.get(produit=produit_mixte, lieu=self.boutique)
        self.assertEqual(stock_apres.quantite, Decimal("0"))
        self.assertEqual(stock_apres.quantite_kg, Decimal("30"))

    def test_vente_kg_superieure_stock_mixte_leve_erreur(self):
        """Vente kg > total kg dispo (sacs+kg) -> ErreurStock."""
        produit_mixte = Produit.objects.create(
            nom="Mil mixte", code="MILMX", unite="sac",
            entreprise=self.ent, poids_par_sac=Decimal("50.000"),
        )
        Stock.objects.create(
            produit=produit_mixte, lieu=self.boutique,
            quantite=Decimal("5"), quantite_kg=Decimal("50"),
        )
        with self.assertRaises(ErreurStock):
            vente_boutique(self.boutique, [(produit_mixte, Decimal("301"), Decimal("200"), "kg")])

    def test_stock_insuffisant_leve_erreur(self):
        """ErreurStock levée si quantité > stock disponible."""
        with self.assertRaises(ErreurStock) as ctx:
            vente_boutique(self.boutique, [(self.produit_kg, Decimal("9999"), Decimal("1"))])
        self.assertIn("insuffisant", str(ctx.exception))

    def test_stock_absent_leve_erreur(self):
        """ErreurStock levée si le produit n'est pas en stock pour ce lieu."""
        produit_absent = Produit.objects.create(nom="Absent", code="ABS", unite="kg", entreprise=self.ent)
        with self.assertRaises(ErreurStock):
            vente_boutique(self.boutique, [(produit_absent, Decimal("1"), Decimal("100"))])

    def test_quantite_zero_leve_erreur(self):
        """ErreurStock levée si quantité <= 0."""
        with self.assertRaises(ErreurStock):
            vente_boutique(self.boutique, [(self.produit_kg, Decimal("0"), Decimal("100"))])

    def test_vente_sur_lieu_usine_refusee(self):
        """Une vente sur un lieu usine est refusée."""
        with self.assertRaises(ErreurStock) as ctx:
            vente_boutique(self.usine, [(self.produit_kg, Decimal("1"), Decimal("100"))])
        self.assertIn("magasin", str(ctx.exception))

    def test_numero_ticket_unique_et_format(self):
        """Le numéro de ticket suit le format KONIS-{CODE}-{DATE}-{SEQ:06d}."""
        ticket, _ = vente_boutique(self.boutique, [(self.produit_kg, Decimal("1"), Decimal("100"))])
        self.assertRegex(ticket.numero, r"^KONIS-TEST-\d{8}-\d{6}$")

    def test_plusieurs_ventes_meme_jour_numeros_distincts(self):
        """Deux ventes le même jour ont des numéros séquentiels distincts."""
        t1, _ = vente_boutique(self.boutique, [(self.produit_kg, Decimal("1"), Decimal("100"))])
        t2, _ = vente_boutique(self.boutique, [(self.produit_kg, Decimal("1"), Decimal("100"))])
        self.assertNotEqual(t1.numero, t2.numero)

    def test_vente_avec_mouture_kg(self):
        """Vente + mouture kg : cout_mouture et montant_total corrects."""
        ticket, _ = vente_boutique(
            self.boutique,
            [(self.produit_kg, Decimal("50"), Decimal("400"))],
            mouture=True,
            prix_mouture_kg=Decimal("50"),
        )
        cout_mouture_attendu = Decimal("50") * Decimal("50")  # 2500
        montant_produits = Decimal("50") * Decimal("400")     # 20000
        self.assertEqual(ticket.cout_mouture, cout_mouture_attendu)
        self.assertEqual(ticket.montant_total, montant_produits + cout_mouture_attendu)
        self.assertTrue(ticket.mouture)

    def test_vente_sans_mouture_cout_zero(self):
        """Sans mouture, cout_mouture = 0."""
        ticket, _ = vente_boutique(
            self.boutique,
            [(self.produit_kg, Decimal("10"), Decimal("300"))],
        )
        self.assertEqual(ticket.cout_mouture, Decimal("0"))
        self.assertFalse(ticket.mouture)

    def test_vente_avec_mouture_multi_unites_total_exact(self):
        """Vente mixte kg + sac : mouture calculée sur le total kg normalisé (formule unifiée)."""
        # produit_kg : 10 × kg = 10 kg
        # produit_sac : 3 × 50 kg/sac = 150 kg  →  total = 160 kg × 25 = 4000
        ticket, _ = vente_boutique(
            self.boutique,
            [
                (self.produit_kg, Decimal("10"), Decimal("500")),
                (self.produit_sac, Decimal("3"), Decimal("1000")),
            ],
            mouture=True,
            prix_mouture_kg=Decimal("25"),
        )
        montant_produits = Decimal("10") * Decimal("500") + Decimal("3") * Decimal("1000")  # 8000
        total_kg = Decimal("10") + Decimal("3") * Decimal("50")  # 160 kg
        cout_mouture = (total_kg * Decimal("25")).quantize(Decimal("0.01"))  # 4000
        self.assertEqual(ticket.cout_mouture, cout_mouture)
        self.assertEqual(ticket.montant_total, montant_produits + cout_mouture)

    def test_vente_avec_mouture_produit_sac_sans_poids_leve_erreur(self):
        """ErreurStock levée si produit.unite='sac' et poids_par_sac non défini."""
        produit_sac_sans_poids = Produit.objects.create(
            nom="Sac sans poids", code="SSP", unite="sac", entreprise=self.ent
        )
        Stock.objects.create(produit=produit_sac_sans_poids, lieu=self.boutique, quantite=Decimal("10"))
        with self.assertRaises(ErreurStock) as ctx:
            vente_boutique(
                self.boutique,
                [(produit_sac_sans_poids, Decimal("1"), Decimal("500"))],
                mouture=True,
                prix_mouture_kg=Decimal("50"),
            )
        self.assertIn("poids_par_sac", str(ctx.exception).lower())

    def test_vente_avec_mouture_refusee_sur_unite_non_supportee(self):
        """La mouture est refusée si l'unité produit n'est pas kg/tonne/sac."""
        produit_piece = Produit.objects.create(nom="Bloc mineral", code="BMIN", unite="piece", entreprise=self.ent)
        Stock.objects.create(produit=produit_piece, lieu=self.boutique, quantite=Decimal("5"))
        with self.assertRaises(ErreurStock) as ctx:
            vente_boutique(
                self.boutique,
                [(produit_piece, Decimal("1"), Decimal("700"))],
                mouture=True,
                prix_mouture_kg=Decimal("10"),
            )
        self.assertIn("non support", str(ctx.exception).lower())


class TestVenteMoutureSeule(APITestCase):
    """Tests du service vente_mouture_seule()."""

    @classmethod
    def setUpTestData(cls):
        cls.ent, cls.boutique, cls.usine, cls.produit_kg, _ = _setup_base()

    def test_mouture_seule_cree_ticket_sans_lignes(self):
        """Mouture-seule crée un ticket sans LigneVente et sans déduire stock."""
        ticket, created = vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("50"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("100"),
        )
        self.assertTrue(created)
        self.assertEqual(ticket.lignes.count(), 0)
        self.assertTrue(ticket.mouture)
        self.assertEqual(ticket.montant_total, Decimal("5000"))  # 50 × 100

    def test_mouture_seule_avec_produit_apporte(self):
        """Le champ produit_apporte est enregistré correctement."""
        ticket, created = vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("100"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("80"),
            produit_apporte="Maïs local",
        )
        self.assertTrue(created)
        self.assertEqual(ticket.produit_apporte, "Maïs local")

    def test_mouture_seule_prix_mouture_kg_set(self):
        """prix_par_kg est toujours stocké dans prix_mouture_kg (champ unifié)."""
        ticket, created = vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("30"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("120"),
        )
        self.assertTrue(created)
        self.assertEqual(ticket.prix_mouture_kg, Decimal("120"))
        self.assertIsNone(ticket.prix_mouture_tonne)
        self.assertIsNone(ticket.prix_mouture_sac)

    def test_mouture_seule_ne_deduit_pas_stock(self):
        """Mouture-seule ne modifie aucun stock."""
        Stock.objects.create(produit=self.produit_kg, lieu=self.boutique, quantite=Decimal("200"))
        stock_avant = Stock.objects.get(produit=self.produit_kg, lieu=self.boutique).quantite
        vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("50"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("100"),
        )
        stock_apres = Stock.objects.get(produit=self.produit_kg, lieu=self.boutique).quantite
        self.assertEqual(stock_avant, stock_apres)

    def test_mouture_seule_fonctionne_sur_usine(self):
        """Mouture-seule fonctionne sur un lieu usine (unité tonne)."""
        # 1 tonne @ 50 FCFA/kg = 1000 kg × 50 = 50 000 FCFA
        ticket, created = vente_mouture_seule(
            lieu=self.usine,
            quantite_apportee=Decimal("1"),
            quantite_achetee=Decimal("0"),
            unite="tonne",
            prix_par_kg=Decimal("50"),
        )
        self.assertTrue(created)
        self.assertEqual(ticket.lieu, self.usine)
        self.assertEqual(ticket.montant_total, Decimal("50000.00"))
        # prix_par_kg stocké dans le champ unifié prix_mouture_kg
        self.assertEqual(ticket.prix_mouture_kg, Decimal("50"))

    def test_montant_total_coherent_avec_champs_db(self):
        """montant_total stocké == cout_mouture (aucun produit)."""
        ticket, created = vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("200"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("75"),
        )
        self.assertTrue(created)
        self.assertEqual(ticket.montant_total, ticket.cout_mouture)
        self.assertEqual(ticket.montant_total, Decimal("200") * Decimal("75"))

    def test_mouture_seule_idempotente(self):
        """Même idempotency_key => même ticket, sans duplication."""
        t1, created1 = vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("10"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("50"),
            idempotency_key="mouture-uniq-1",
        )
        t2, created2 = vente_mouture_seule(
            lieu=self.boutique,
            quantite_apportee=Decimal("10"),
            quantite_achetee=Decimal("0"),
            unite="kg",
            prix_par_kg=Decimal("50"),
            idempotency_key="mouture-uniq-1",
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(
            Ticket.objects.filter(lieu=self.boutique, idempotency_key="mouture-uniq-1").count(),
            1,
        )
