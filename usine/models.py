from django.db import models
from django.db.models import CheckConstraint, Q

from core.models import Lieu
from inventaire.models import Transfert
from produits.models import Produit


class LotProduction(models.Model):
    """Lot de production d'un produit fini à l'usine."""

    UNITE_KG = "kg"
    UNITE_TONNES = "tonnes"
    UNITE_CHOICES = [
        (UNITE_KG, "Kilogrammes"),
        (UNITE_TONNES, "Tonnes"),
    ]

    nom_lot = models.CharField(max_length=100, unique=True)
    lieu_usine = models.ForeignKey(Lieu, on_delete=models.PROTECT, related_name="lots_production")
    produit_fini = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="lots_production")
    created_by = models.ForeignKey(
        "core.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="lots_crees"
    )
    quantite_sacs = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Nombre de sacs")
    poids = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Poids total")
    unite_poids = models.CharField(
        max_length=10, choices=UNITE_CHOICES, default=UNITE_KG, verbose_name="Unité de poids"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lot de production"
        verbose_name_plural = "Lots de production"
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(condition=Q(quantite_sacs__gt=0), name="lot_quantite_sacs_positive"),
            CheckConstraint(condition=Q(poids__gte=0), name="lot_poids_non_negatif"),
        ]
        indexes = [
            models.Index(fields=["lieu_usine", "created_at"]),
            models.Index(fields=["produit_fini", "created_at"]),
        ]

    def __str__(self):
        return f"{self.nom_lot} - {self.produit_fini.nom}"


class TransfertCession(models.Model):
    """Cession d'un lot vers une boutique avec prix de vente par sac."""

    lot = models.ForeignKey(LotProduction, on_delete=models.PROTECT, related_name="cessions")
    boutique = models.ForeignKey(Lieu, on_delete=models.PROTECT, related_name="cessions_reception")
    quantite_sacs = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Nombre de sacs transférés")
    poids_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Poids total transféré"
    )
    prix_par_sac = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Prix de vente par sac")
    transfert = models.ForeignKey(
        Transfert, on_delete=models.SET_NULL, null=True, blank=True, related_name="cessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transfert de cession"
        verbose_name_plural = "Transferts de cession"
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(condition=Q(quantite_sacs__gt=0), name="cession_quantite_sacs_positive"),
            CheckConstraint(condition=Q(prix_par_sac__gte=0), name="cession_prix_non_negatif"),
            CheckConstraint(condition=Q(poids_total__gte=0), name="cession_poids_non_negatif"),
        ]
        indexes = [
            models.Index(fields=["lot", "created_at"]),
            models.Index(fields=["boutique", "created_at"]),
        ]

    @property
    def montant_cession(self):
        return self.quantite_sacs * self.prix_par_sac

    def __str__(self):
        return f"{self.lot.nom_lot} → {self.boutique.nom} ({self.quantite_sacs} sacs)"


class TransfertInterUsine(models.Model):
    """Transfert de produits finis d'une usine vers une autre usine."""

    lot = models.ForeignKey(LotProduction, on_delete=models.PROTECT, related_name="transferts_inter_usine")
    usine_destination = models.ForeignKey(
        Lieu,
        on_delete=models.PROTECT,
        related_name="transferts_inter_usine_entrants",
        limit_choices_to={"type_lieu": Lieu.TYPE_USINE},
    )
    quantite_sacs = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Nombre de sacs transférés")
    poids_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Poids total transféré")
    prix_par_sac = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Prix par sac")
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "core.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="transferts_inter_usine_crees"
    )
    transfert = models.ForeignKey(
        Transfert, on_delete=models.SET_NULL, null=True, blank=True, related_name="inter_usine_cessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transfert inter-usines"
        verbose_name_plural = "Transferts inter-usines"
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(condition=Q(quantite_sacs__gt=0), name="inter_usine_quantite_sacs_positive"),
            CheckConstraint(condition=Q(prix_par_sac__gte=0), name="inter_usine_prix_non_negatif"),
            CheckConstraint(condition=Q(poids_total__gte=0), name="inter_usine_poids_non_negatif"),
        ]
        indexes = [
            models.Index(fields=["lot", "created_at"]),
            models.Index(fields=["usine_destination", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    @property
    def montant_transfert(self):
        return self.quantite_sacs * self.prix_par_sac

    def __str__(self):
        return f"{self.lot.nom_lot} → {self.usine_destination.nom} ({self.quantite_sacs} sacs)"
