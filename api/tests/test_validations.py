"""
Tests unitaires — validations serializers KONIS.
Couvre : VenteBoutiqueCreateSerializer, FactureCreateSerializer,
         LotProductionCreateSerializer, TransfertCessionCreateSerializer,
         TransfertInterUsineCreateSerializer, MoutureSeuleSerializer.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from api.serializers import (
    FactureCreateSerializer,
    LotProductionCreateSerializer,
    MoutureSeuleSerializer,
    TransfertCessionCreateSerializer,
    TransfertInterUsineCreateSerializer,
    VenteBoutiqueCreateSerializer,
)
from core.models import Entreprise, Lieu
from produits.models import Produit
from usine.models import LotProduction


def _make_vente_payload(quantite="10", prix_unitaire="500", produit_id=1):
    return {
        "lignes": [{"produit": produit_id, "quantite": quantite, "prix_unitaire": prix_unitaire}]
    }


class TestVenteBoutiqueCreateSerializer(APITestCase):
    """Validation de VenteBoutiqueCreateSerializer.validate_lignes()."""

    @classmethod
    def setUpTestData(cls):
        ent = Entreprise.objects.create(nom="ENT Val")
        cls.produit = Produit.objects.create(nom="Test", code="TST", unite="kg", entreprise=ent)

    def _ser(self, data):
        return VenteBoutiqueCreateSerializer(data=data)

    def test_ligne_valide_passe(self):
        """Une ligne correcte passe la validation."""
        ser = self._ser(_make_vente_payload(produit_id=self.produit.pk))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_prix_zero_rejete(self):
        """Prix unitaire = 0 est refusé."""
        ser = self._ser(_make_vente_payload(prix_unitaire="0", produit_id=self.produit.pk))
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)
        error_text = str(ser.errors["lignes"])
        self.assertIn("0", error_text)

    def test_prix_negatif_rejete(self):
        """Prix unitaire < 0 est refusé."""
        ser = self._ser(_make_vente_payload(prix_unitaire="-100", produit_id=self.produit.pk))
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)

    def test_quantite_zero_rejetee(self):
        """Quantité = 0 est refusée."""
        ser = self._ser(_make_vente_payload(quantite="0", produit_id=self.produit.pk))
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)

    def test_quantite_negative_rejetee(self):
        """Quantité négative est refusée."""
        ser = self._ser(_make_vente_payload(quantite="-5", produit_id=self.produit.pk))
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)

    def test_champ_manquant_rejete(self):
        """Une ligne sans 'prix_unitaire' est refusée."""
        ser = self._ser({
            "lignes": [{"produit": self.produit.pk, "quantite": "10"}]
        })
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)

    def test_mouture_sans_prix_rejetee(self):
        """Mouture=True sans aucun prix de mouture est refusé (validate())."""
        ser = self._ser({
            "lignes": [{"produit": self.produit.pk, "quantite": "10", "prix_unitaire": "500"}],
            "mouture": True,
        })
        self.assertFalse(ser.is_valid())

    def test_mouture_avec_prix_acceptee(self):
        """Mouture=True avec prix_mouture_kg est valide."""
        ser = self._ser({
            "lignes": [{"produit": self.produit.pk, "quantite": "10", "prix_unitaire": "500"}],
            "mouture": True,
            "prix_mouture_kg": "50",
        })
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_valeurs_decimal_string_acceptees(self):
        """Les valeurs numériques sous forme de string sont acceptées."""
        ser = self._ser(_make_vente_payload(quantite="10.5", prix_unitaire="1500.50", produit_id=self.produit.pk))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_valeurs_non_numeriques_rejetees(self):
        """Des valeurs non-numériques comme 'abc' sont refusées."""
        ser = self._ser(_make_vente_payload(quantite="abc", prix_unitaire="xyz", produit_id=self.produit.pk))
        self.assertFalse(ser.is_valid())


class TestFactureCreateSerializer(APITestCase):
    """Validation de FactureCreateSerializer.validate_lignes()."""

    @classmethod
    def setUpTestData(cls):
        ent = Entreprise.objects.create(nom="ENT Fact")
        cls.produit = Produit.objects.create(nom="P Fact", code="PFACT", unite="kg", entreprise=ent)

    def _ligne(self, quantite="5", prix="1000", description="Service"):
        return {"description": description, "quantite": quantite, "prix_unitaire": prix}

    def _ser(self, lignes):
        return FactureCreateSerializer(data={"lignes": lignes})

    def test_ligne_valide_passe(self):
        ser = self._ser([self._ligne()])
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_prix_zero_rejete(self):
        """Prix unitaire = 0 refusé dans une facture."""
        ser = self._ser([self._ligne(prix="0")])
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)

    def test_prix_negatif_rejete(self):
        ser = self._ser([self._ligne(prix="-100")])
        self.assertFalse(ser.is_valid())
        self.assertIn("lignes", ser.errors)

    def test_quantite_zero_rejetee(self):
        ser = self._ser([self._ligne(quantite="0")])
        self.assertFalse(ser.is_valid())

    def test_description_manquante_rejetee(self):
        ser = self._ser([{"quantite": "5", "prix_unitaire": "1000"}])
        self.assertFalse(ser.is_valid())

    def test_liste_vide_rejetee(self):
        """Une facture sans lignes est refusée (allow_empty=False)."""
        ser = self._ser([])
        self.assertFalse(ser.is_valid())


class TestLotProductionCreateSerializer(APITestCase):
    """Validation des poids dans LotProductionCreateSerializer."""

    @classmethod
    def setUpTestData(cls):
        cls.ent = Entreprise.objects.create(nom="ENT Lot")
        cls.usine = Lieu.objects.create(
            entreprise=cls.ent, nom="Usine Lot", code="ULT", type_lieu=Lieu.TYPE_USINE
        )
        cls.produit = Produit.objects.create(
            nom="P Lot", code="PLOT", unite="sac",
            entreprise=cls.ent, category=Produit.CATEGORY_FINISHED,
        )

    def _ser(self, data):
        from unittest.mock import MagicMock
        request = MagicMock()
        request.user.entreprise = self.ent
        request.user.entreprise_id = self.ent.pk
        return LotProductionCreateSerializer(data=data, context={"request": request})

    def _base(self, **extra):
        data = {
            "nom_lot": "LOT-TEST",
            "lieu_usine": self.usine.pk,
            "produit_fini": self.produit.pk,
            "quantite_sacs": "100",
            "poids": "0",
            "unite_poids": "kg",
        }
        data.update(extra)
        return data

    def test_lot_valide_passe(self):
        """Lot avec poids cohérent (50 kg/sac) est valide."""
        ser = self._ser(self._base(quantite_sacs="100", poids="5000", unite_poids="kg"))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_poids_coherent_tonnes_passe(self):
        """Lot avec 5 tonnes pour 100 sacs = 50 kg/sac, valide."""
        ser = self._ser(self._base(quantite_sacs="100", poids="5", unite_poids="tonnes"))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_poids_incoherent_kg_rejete(self):
        """Poids > 1000 kg/sac est refusé."""
        # 200000 kg / 100 sacs = 2000 kg/sac → trop élevé
        ser = self._ser(self._base(quantite_sacs="100", poids="200000", unite_poids="kg"))
        self.assertFalse(ser.is_valid())
        self.assertIn("poids", str(ser.errors))

    def test_poids_incoherent_tonnes_rejete(self):
        """200 tonnes pour 100 sacs = 2000 kg/sac → refusé."""
        ser = self._ser(self._base(quantite_sacs="100", poids="200", unite_poids="tonnes"))
        self.assertFalse(ser.is_valid())
        self.assertIn("poids", str(ser.errors))

    def test_poids_zero_non_valide(self):
        """Poids = 0 → validation ignorée (pas d'erreur de cohérence)."""
        ser = self._ser(self._base(quantite_sacs="100", poids="0", unite_poids="kg"))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_poids_exactement_1000_kg_par_sac_passe(self):
        """Exactement 1000 kg/sac (limite) est accepté."""
        # 100000 kg / 100 sacs = 1000 kg/sac
        ser = self._ser(self._base(quantite_sacs="100", poids="100000", unite_poids="kg"))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_poids_1001_kg_par_sac_rejete(self):
        """1001 kg/sac dépasse la limite."""
        # 100100 kg / 100 sacs = 1001 kg/sac
        ser = self._ser(self._base(quantite_sacs="100", poids="100100", unite_poids="kg"))
        self.assertFalse(ser.is_valid())

    def test_quantite_sacs_zero_rejete(self):
        """quantite_sacs = 0 est refusé (min_value=0.01)."""
        ser = self._ser(self._base(quantite_sacs="0"))
        self.assertFalse(ser.is_valid())


class TestTransfertCessionCreateSerializer(APITestCase):
    """Validation des poids dans TransfertCessionCreateSerializer."""

    @classmethod
    def setUpTestData(cls):
        ent = Entreprise.objects.create(nom="ENT Ces")
        usine = Lieu.objects.create(
            entreprise=ent, nom="Usine Ces", code="UCE", type_lieu=Lieu.TYPE_USINE
        )
        cls.boutique = Lieu.objects.create(
            entreprise=ent, nom="Boutique Ces", code="BCE", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.produit = Produit.objects.create(nom="P Ces", code="PCES", unite="sac", entreprise=ent)
        cls.lot = LotProduction.objects.create(
            nom_lot="LOT-CES",
            lieu_usine=usine,
            produit_fini=cls.produit,
            quantite_sacs=Decimal("500"),
            poids=Decimal("25000"),
            unite_poids="kg",
        )

    def _ser(self, data):
        return TransfertCessionCreateSerializer(data=data)

    def _base(self, **extra):
        data = {
            "lot": self.lot.pk,
            "boutique": self.boutique.pk,
            "quantite_sacs": "50",
            "poids_total": "2500",
            "prix_par_sac": "5000",
        }
        data.update(extra)
        return data

    def test_cession_valide_passe(self):
        """Cession avec poids cohérent (50 kg/sac) est valide."""
        ser = self._ser(self._base())
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_poids_incoherent_rejete(self):
        """Poids > 1000 kg/sac refusé dans une cession."""
        # 200000 kg pour 50 sacs = 4000 kg/sac
        ser = self._ser(self._base(poids_total="200000"))
        self.assertFalse(ser.is_valid())
        self.assertIn("poids_total", str(ser.errors))

    def test_poids_zero_accepte(self):
        """poids_total = 0 ignore la validation de cohérence."""
        ser = self._ser(self._base(poids_total="0"))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_quantite_sacs_zero_rejete(self):
        """quantite_sacs = 0 est refusé."""
        ser = self._ser(self._base(quantite_sacs="0"))
        self.assertFalse(ser.is_valid())


class TestTransfertInterUsineCreateSerializer(APITestCase):
    """Validation des poids dans TransfertInterUsineCreateSerializer."""

    @classmethod
    def setUpTestData(cls):
        ent = Entreprise.objects.create(nom="ENT IU")
        cls.usine_src = Lieu.objects.create(
            entreprise=ent, nom="Usine IU Src", code="UISC", type_lieu=Lieu.TYPE_USINE
        )
        cls.usine_dst = Lieu.objects.create(
            entreprise=ent, nom="Usine IU Dst", code="UIDS", type_lieu=Lieu.TYPE_USINE
        )
        cls.produit = Produit.objects.create(nom="P IU", code="PIU", unite="sac", entreprise=ent)
        cls.lot = LotProduction.objects.create(
            nom_lot="LOT-IU",
            lieu_usine=cls.usine_src,
            produit_fini=cls.produit,
            quantite_sacs=Decimal("200"),
            poids=Decimal("10000"),
            unite_poids="kg",
        )

    def _ser(self, data):
        return TransfertInterUsineCreateSerializer(data=data)

    def _base(self, **extra):
        data = {
            "lot": self.lot.pk,
            "usine_destination": self.usine_dst.pk,
            "quantite_sacs": "20",
            "poids_total": "1000",
            "prix_par_sac": "0",
        }
        data.update(extra)
        return data

    def test_transfert_inter_usine_valide_passe(self):
        """Transfert inter-usine avec poids cohérent est valide."""
        ser = self._ser(self._base())
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_poids_incoherent_rejete(self):
        """Poids > 1000 kg/sac refusé dans un transfert inter-usine."""
        # 300000 kg pour 20 sacs = 15000 kg/sac
        ser = self._ser(self._base(poids_total="300000"))
        self.assertFalse(ser.is_valid())
        self.assertIn("poids_total", str(ser.errors))

    def test_poids_zero_accepte(self):
        """poids_total = 0 ignore la validation de cohérence."""
        ser = self._ser(self._base(poids_total="0"))
        self.assertTrue(ser.is_valid(), ser.errors)


class TestMoutureSeuleSerializer(APITestCase):
    """Validation de MoutureSeuleSerializer."""

    def _ser(self, data):
        return MoutureSeuleSerializer(data=data)

    def test_donnees_valides_passent(self):
        """Données correctes passent la validation."""
        ser = self._ser({"quantite_apportee": "50", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "100"})
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_quantite_zero_rejetee(self):
        """apportee=0 ET achetee=0 → refusé (total must be > 0)."""
        ser = self._ser({"quantite_apportee": "0", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "100"})
        self.assertFalse(ser.is_valid())

    def test_unite_invalide_rejetee(self):
        """Une unité non autorisée est refusée."""
        ser = self._ser({"quantite_apportee": "10", "quantite_achetee": "0", "unite": "litre", "prix_par_kg": "50"})
        self.assertFalse(ser.is_valid())

    def test_unites_autorisees(self):
        """kg et tonne sont validés sans produit_id ; sac requiert produit_id."""
        for unite in ("kg", "tonne"):
            ser = self._ser({"quantite_apportee": "10", "quantite_achetee": "0", "unite": unite, "prix_par_kg": "50"})
            self.assertTrue(ser.is_valid(), f"Échec pour unite={unite}: {ser.errors}")
        # sac nécessite produit_id (n'importe quel entier passe la validation serializer)
        ser_sac = self._ser({
            "quantite_apportee": "2", "quantite_achetee": "0",
            "unite": "sac", "prix_par_kg": "50", "produit_id": 1,
        })
        self.assertTrue(ser_sac.is_valid(), f"Échec pour unite=sac: {ser_sac.errors}")

    def test_sac_sans_produit_id_rejete(self):
        """unite=sac sans produit_id est refusé."""
        ser = self._ser({"quantite_apportee": "2", "quantite_achetee": "0", "unite": "sac", "prix_par_kg": "50"})
        self.assertFalse(ser.is_valid())

    def test_produit_nom_optionnel(self):
        """Le champ produit_nom est optionnel et a une valeur par défaut vide."""
        ser = self._ser({"quantite_apportee": "30", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "75"})
        self.assertTrue(ser.is_valid(), ser.errors)
        self.assertEqual(ser.validated_data.get("produit_nom", ""), "")

    def test_produit_nom_enregistre(self):
        """produit_nom est bien présent dans validated_data si fourni."""
        ser = self._ser({
            "quantite_apportee": "30", "quantite_achetee": "0",
            "unite": "kg", "prix_par_kg": "75",
            "produit_nom": "Maïs importé",
        })
        self.assertTrue(ser.is_valid(), ser.errors)
        self.assertEqual(ser.validated_data["produit_nom"], "Maïs importé")

    def test_prix_par_kg_zero_accepte(self):
        """prix_par_kg = 0 est autorisé (mouture offerte — min_value=0)."""
        ser = self._ser({"quantite_apportee": "10", "quantite_achetee": "0", "unite": "kg", "prix_par_kg": "0"})
        self.assertTrue(ser.is_valid(), ser.errors)
