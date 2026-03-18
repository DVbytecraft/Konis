from decimal import Decimal

from django.db import models
from django.db.models import Q, UniqueConstraint

from core.models import CustomUser, Lieu
from produits.models import Produit


class Ticket(models.Model):
    """Ticket de vente (ticket thermique) par lieu. Numéro obligatoire, unique (lieu, numero)."""
    lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="tickets"
    )
    date = models.DateTimeField(auto_now_add=True)
    numero = models.CharField(max_length=50)
    idempotency_key = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Cle idempotente de creation (anti double soumission).",
    )

    # ── Mouture (service d'écrasement optionnel) ───────────────────────────────
    produit_apporte = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="Produit apporté par le client",
    )
    mouture = models.BooleanField(default=False, verbose_name="Mouture demandée")
    prix_mouture_kg = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Prix mouture / kg",
    )
    prix_mouture_tonne = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Prix mouture / tonne",
    )
    prix_mouture_sac = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Prix mouture / sac",
    )
    quantite_apportee_client = models.DecimalField(
        max_digits=12, decimal_places=3,
        default=Decimal("0"), blank=True,
        verbose_name="Quantité grain apportée par le client (kg, normalisé)",
        help_text="Toujours stocké en kg après normalisation.",
    )
    cout_mouture = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        verbose_name="Coût total mouture",
    )
    # montant_total = sous-total produits + cout_mouture
    montant_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        verbose_name="Montant total (produits + mouture)",
    )

    class Meta:
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        ordering = ["-date"]
        constraints = [
            UniqueConstraint(fields=["lieu", "numero"], name="unique_ticket_lieu_numero"),
            UniqueConstraint(
                fields=["lieu", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_ticket_lieu_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["lieu", "date"]),
            models.Index(fields=["date"]),
            models.Index(fields=["numero"]),
        ]

    def __str__(self):
        return f"Ticket #{self.numero} ({self.lieu})"


class TicketReprint(models.Model):
    """Log de réimpression d'un ticket. Chaque réimpression est tracée."""
    ticket = models.ForeignKey(
        Ticket, on_delete=models.PROTECT, related_name="reprints"
    )
    utilisateur = models.ForeignKey(
        "core.CustomUser", on_delete=models.SET_NULL,
        null=True, related_name="ticket_reprints",
    )
    boutique = models.ForeignKey(
        "core.Lieu", on_delete=models.PROTECT, related_name="ticket_reprints"
    )
    date_heure = models.DateTimeField(auto_now_add=True)
    motif = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Réimpression de ticket"
        verbose_name_plural = "Réimpressions de tickets"
        ordering = ["-date_heure"]
        indexes = [
            models.Index(fields=["ticket", "date_heure"]),
            models.Index(fields=["utilisateur", "date_heure"]),
        ]

    def __str__(self):
        return f"Réimpression ticket #{self.ticket.numero} par {self.utilisateur_id}"


class LigneVente(models.Model):
    """Ligne d'une vente : produit, quantité, prix unitaire."""
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="lignes"
    )
    produit = models.ForeignKey(
        Produit, on_delete=models.PROTECT, related_name="lignes_vente"
    )
    quantite = models.DecimalField(max_digits=12, decimal_places=2)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de vente"
        verbose_name_plural = "Lignes de vente"

    def __str__(self):
        return f"{self.produit} x {self.quantite} @ {self.prix_unitaire}"

    @property
    def total(self):
        return self.quantite * self.prix_unitaire


class Facture(models.Model):
    """Facture A4 (transverse) utilisable par admin/comptable/usine/boutique."""
    SOURCE_ADMIN = "admin"
    SOURCE_COMPTABLE = "comptable"
    SOURCE_USINE = "usine"
    SOURCE_BOUTIQUE = "boutique"
    SOURCE_CHOICES = [
        (SOURCE_ADMIN, "Admin"),
        (SOURCE_COMPTABLE, "Comptable"),
        (SOURCE_USINE, "Usine"),
        (SOURCE_BOUTIQUE, "Boutique"),
    ]

    lieu = models.ForeignKey(Lieu, on_delete=models.PROTECT, related_name="factures")
    numero = models.CharField(max_length=50)
    date = models.DateTimeField(auto_now_add=True)
    source_role = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="factures_creees",
    )
    client_nom = models.CharField(max_length=255, blank=True, default="")
    client_contact = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"
        ordering = ["-date"]
        constraints = [
            UniqueConstraint(fields=["lieu", "numero"], name="unique_facture_lieu_numero"),
        ]
        indexes = [
            models.Index(fields=["lieu", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"Facture #{self.numero} ({self.lieu})"


class LigneFacture(models.Model):
    """Ligne d'une facture (produit optionnel pour lignes libres)."""
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(
        Produit,
        on_delete=models.PROTECT,
        related_name="lignes_facture",
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=255)
    quantite = models.DecimalField(max_digits=12, decimal_places=2)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de facture"
        verbose_name_plural = "Lignes de facture"

    def __str__(self):
        return f"{self.description} x {self.quantite} @ {self.prix_unitaire}"

    @property
    def total(self):
        return self.quantite * self.prix_unitaire
