from django.db import models
from django.db.models import CheckConstraint, Q

from core.models import Lieu


class CategorieDepense(models.Model):
    """Catégorie de dépense."""
    nom = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Catégorie de dépense"
        verbose_name_plural = "Catégories de dépense"


class Depense(models.Model):
    """Dépense saisie par lieu."""
    lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="depenses"
    )
    categorie = models.ForeignKey(
        CategorieDepense, on_delete=models.PROTECT, related_name="depenses"
    )
    production_order = models.ForeignKey(
        "usine.LotProduction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depenses",
    )
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    libelle = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ["-date"]
        constraints = [
            CheckConstraint(condition=Q(montant__gte=0), name="depense_montant_positive"),
        ]
        indexes = [
            models.Index(fields=["lieu", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"{self.lieu} - {self.montant} ({self.date})"
