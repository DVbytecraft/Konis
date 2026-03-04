"""
Tests contrainte dépense : montant >= 0.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import Entreprise, Lieu
from depenses.models import CategorieDepense, Depense


class DepenseConstraintTests(TestCase):
    """Test contrainte DB depense montant >= 0."""

    @classmethod
    def setUpTestData(cls):
        entreprise = Entreprise.objects.create(nom="KONIS")
        cls.lieu = Lieu.objects.create(
            entreprise=entreprise, nom="Boutique", type_lieu=Lieu.TYPE_MAGASIN
        )
        cls.cat = CategorieDepense.objects.create(nom="Divers")

    def test_depense_negative_refus(self):
        """Dépense avec montant négatif -> IntegrityError ou ValidationError."""
        from django.core.exceptions import ValidationError

        dep = Depense(
            lieu=self.lieu,
            categorie=self.cat,
            montant=Decimal("-10"),
            date="2026-02-08",
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            dep.save()
