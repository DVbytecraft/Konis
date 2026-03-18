from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint

from core.models import Lieu


def _default_entreprise_id():
    from core.models import Entreprise

    ent = Entreprise.objects.order_by("id").first()
    if ent:
        return ent.id
    raise ValueError(
        "Aucune entreprise trouvée. Créez une entreprise avant de créer des catégories de dépense."
    )


class CategorieDepense(models.Model):
    """Catégorie de dépense."""
    entreprise = models.ForeignKey(
        "core.Entreprise",
        on_delete=models.PROTECT,
        related_name="categories_depenses",
        default=_default_entreprise_id,
        db_index=True,
    )
    nom = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Catégorie de dépense"
        verbose_name_plural = "Catégories de dépense"
        indexes = [
            models.Index(fields=["entreprise", "nom"]),
        ]


class Depense(models.Model):
    """Dépense — rattachée à un lieu ou sans lieu (Autre)."""
    entreprise = models.ForeignKey(
        "core.Entreprise",
        on_delete=models.PROTECT,
        related_name="depenses",
        null=True,
        blank=True,
        db_index=True,
    )
    lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="depenses",
        null=True, blank=True,
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
    updated_at = models.DateTimeField(auto_now=True)
    idempotency_key = models.CharField(
        max_length=128, null=True, blank=True, db_index=True,
        help_text="Clé idempotente de création (anti double soumission).",
    )

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ["-date"]
        constraints = [
            CheckConstraint(condition=Q(montant__gte=0), name="depense_montant_positive"),
            UniqueConstraint(
                fields=["entreprise", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_depense_entreprise_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["entreprise", "date"]),
            models.Index(fields=["lieu", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        lieu_label = self.lieu.nom if self.lieu_id else "Autre"
        return f"{lieu_label} - {self.montant} ({self.date})"
