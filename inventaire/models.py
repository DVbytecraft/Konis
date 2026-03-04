from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint

from core.models import Lieu
from produits.models import Produit


class Stock(models.Model):
    """Stock d'un produit dans un lieu. Quantité toujours >= 0."""
    produit = models.ForeignKey(
        Produit, on_delete=models.CASCADE, related_name="stocks"
    )
    lieu = models.ForeignKey(
        Lieu, on_delete=models.CASCADE, related_name="stocks"
    )
    quantite = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        constraints = [
            UniqueConstraint(fields=["produit", "lieu"], name="unique_stock_produit_lieu"),
            CheckConstraint(condition=Q(quantite__gte=0), name="stock_quantite_positive"),
        ]
        indexes = [
            models.Index(fields=["produit", "lieu"]),
            models.Index(fields=["lieu"]),
        ]

    def __str__(self):
        return f"{self.produit} @ {self.lieu}: {self.quantite}"

    def save(self, *args, **kwargs):
        if self.quantite < 0:
            raise ValidationError(
                {"quantite": "Le stock ne peut pas être négatif."}
            )
        super().save(*args, **kwargs)


class Transfert(models.Model):
    """Transfert de stock d'un lieu vers un autre (ex. usine → magasin)."""
    from_lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="transferts_sortants"
    )
    to_lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="transferts_entrants"
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transfert"
        verbose_name_plural = "Transferts"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["from_lieu", "date"]),
            models.Index(fields=["to_lieu", "date"]),
        ]

    def __str__(self):
        return f"Transfert {self.from_lieu} → {self.to_lieu} ({self.date})"


class MouvementStock(models.Model):
    """Ligne d'un transfert : produit et quantité déplacée."""
    transfert = models.ForeignKey(
        Transfert, on_delete=models.CASCADE, related_name="mouvements"
    )
    produit = models.ForeignKey(
        Produit, on_delete=models.PROTECT, related_name="mouvements_transfert"
    )
    quantite = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    production_order = models.ForeignKey(
        "usine.LotProduction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mouvements_transfert",
    )

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        constraints = [
            CheckConstraint(condition=Q(quantite__gt=0), name="mouvement_quantite_strictement_positive"),
            CheckConstraint(condition=Q(unit_price__gte=0), name="mouvement_unit_price_non_negatif"),
        ]

    def __str__(self):
        return f"{self.produit} x {self.quantite} (transfert #{self.transfert_id})"

    def save(self, *args, **kwargs):
        if self.quantite <= 0:
            raise ValidationError(
                {"quantite": "La quantité doit être strictement positive."}
            )
        super().save(*args, **kwargs)


class AchatUsine(models.Model):
    """Enregistrement d'achat d'intrant à l'usine (pour comptabilité)."""

    UNITE_SACS = "sacs"
    UNITE_KG = "kg"
    UNITE_TONNES = "tonnes"
    UNITE_CHOICES = [
        (UNITE_SACS, "Sacs"),
        (UNITE_KG, "Kilogrammes"),
        (UNITE_TONNES, "Tonnes"),
    ]

    lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="achats_usine"
    )
    produit_nom = models.CharField(max_length=255, verbose_name="Produit acheté")
    quantite = models.DecimalField(max_digits=12, decimal_places=2)
    unite = models.CharField(max_length=10, choices=UNITE_CHOICES, default=UNITE_SACS)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prix_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="achats_usine_crees",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Achat usine"
        verbose_name_plural = "Achats usine"
        ordering = ["-date"]
        constraints = [
            CheckConstraint(condition=Q(quantite__gt=0), name="achatusine_quantite_positive"),
            CheckConstraint(condition=Q(prix_unitaire__gte=0), name="achatusine_prix_unitaire_positif"),
            CheckConstraint(condition=Q(prix_total__gte=0), name="achatusine_prix_total_positif"),
        ]
        indexes = [
            models.Index(fields=["lieu", "date"]),
        ]

    def __str__(self):
        return f"Achat {self.produit_nom} x {self.quantite} {self.unite} @ {self.lieu}"

    def save(self, *args, **kwargs):
        # Auto-calculer prix_total si pas fourni ou incohérent
        if self.prix_unitaire and self.quantite:
            from decimal import Decimal
            calculated = Decimal(str(self.quantite)) * Decimal(str(self.prix_unitaire))
            if not self.prix_total or self.prix_total == 0:
                self.prix_total = calculated
        super().save(*args, **kwargs)
