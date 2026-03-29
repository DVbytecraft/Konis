from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import CheckConstraint, Q, UniqueConstraint

from core.models import Lieu
from produits.models import Produit


class Stock(models.Model):
    """
    Stock d'un produit dans un lieu.

    Dual tracking sacs / kg :
      - quantite     : nombre d'unités dans l'unité native du produit
                       (sacs entiers si produit.unite='sac', kg sinon)
      - quantite_kg  : kg issus de sacs fractionnés/convertis (toujours >= 0)
                       significatif uniquement si produit.poids_par_sac est défini

    Conversion : convertir_sacs_en_kg(n)
      quantite -= n ; quantite_kg += n * produit.poids_par_sac
      quantite reste en "sacs", quantite_kg en "kg"

    Affichage boutique : "{quantite} sacs + {quantite_kg} kg"
    """
    produit = models.ForeignKey(
        Produit, on_delete=models.PROTECT, related_name="stocks"
    )
    lieu = models.ForeignKey(
        Lieu, on_delete=models.PROTECT, related_name="stocks"
    )
    quantite = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    quantite_kg = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0"),
        verbose_name="Kg supplémentaires (sacs convertis)",
        help_text="Kg issus de la conversion de sacs entiers. 0 si aucune conversion.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock"
        verbose_name_plural = "Stocks"
        ordering = ["-id"]
        constraints = [
            UniqueConstraint(fields=["produit", "lieu"], name="unique_stock_produit_lieu"),
            CheckConstraint(condition=Q(quantite__gte=0),    name="stock_quantite_positive"),
            CheckConstraint(condition=Q(quantite_kg__gte=0), name="stock_quantite_kg_positive"),
        ]
        indexes = [
            models.Index(fields=["produit", "lieu"]),
            models.Index(fields=["lieu"]),
        ]

    def __str__(self):
        pps = getattr(self.produit, "poids_par_sac", None)
        if pps and self.quantite_kg > 0:
            return f"{self.produit} @ {self.lieu}: {self.quantite} sacs + {self.quantite_kg} kg"
        return f"{self.produit} @ {self.lieu}: {self.quantite}"

    def save(self, *args, **kwargs):
        if self.quantite < 0:
            raise ValidationError({"quantite": "Le stock ne peut pas être négatif."})
        if self.quantite_kg < 0:
            raise ValidationError({"quantite_kg": "Le stock en kg ne peut pas être négatif."})
        super().save(*args, **kwargs)

    def convertir_sacs_en_kg(self, nombre_sacs: int) -> Decimal:
        """
        Convertit nombre_sacs sacs en kg de façon atomique et sans race condition.
        Décrémente quantite (sacs), incrémente quantite_kg.
        Retourne le nombre de kg générés.
        Lève ValueError si le produit n'a pas poids_par_sac défini,
        ou si le stock en sacs est insuffisant.
        """
        if nombre_sacs <= 0:
            raise ValueError("Le nombre de sacs à convertir doit être > 0.")
        with transaction.atomic():
            # Re-fetch avec SELECT FOR UPDATE pour sérialiser les conversions concurrentes.
            stock = Stock.objects.select_for_update().get(pk=self.pk)
            pps = stock.produit.poids_par_sac
            if not pps:
                raise ValueError(
                    f"Le produit '{stock.produit.nom}' n'a pas de poids_par_sac défini."
                )
            if Decimal(str(nombre_sacs)) > stock.quantite:
                raise ValueError(
                    f"Stock insuffisant : {stock.quantite} sac(s) disponible(s), "
                    f"demande {nombre_sacs}."
                )
            kg = Decimal(str(nombre_sacs)) * pps
            stock.quantite    -= Decimal(str(nombre_sacs))
            stock.quantite_kg += kg
            stock.save(update_fields=["quantite", "quantite_kg", "updated_at"])
            # Sync back so the caller sees the updated values.
            self.quantite    = stock.quantite
            self.quantite_kg = stock.quantite_kg
        return kg


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
        Transfert, on_delete=models.PROTECT, related_name="mouvements"
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


class AchatMPSL(models.Model):
    """
    Achat de produit au dépôt MPSL.
    Contrairement à AchatUsine (purement comptable), AchatMPSL IMPACTE le stock.
    Flux : Fournisseur → MPSL (avec prix d'achat, quantité, produit FK).
    """

    UNITE_SACS = "sacs"
    UNITE_KG = "kg"
    UNITE_TONNES = "tonnes"
    UNITE_CHOICES = [
        (UNITE_SACS, "Sacs"),
        (UNITE_KG, "Kilogrammes"),
        (UNITE_TONNES, "Tonnes"),
    ]

    # ── Types de paiement ───────────────────────────────────────────────────
    TYPE_CASH    = "cash"
    TYPE_CREDIT  = "credit"
    TYPE_PARTIEL = "partiel"
    TYPE_PAIEMENT_CHOICES = [
        (TYPE_CASH,    "Cash"),
        (TYPE_CREDIT,  "Crédit"),
        (TYPE_PARTIEL, "Partiel"),
    ]

    lieu = models.ForeignKey(
        Lieu,
        on_delete=models.PROTECT,
        related_name="achats_mpsl",
        limit_choices_to={"type_lieu": "mpsl"},
    )
    fournisseur = models.ForeignKey(
        "finance.Creancier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="achats_mpsl",
        help_text="Fournisseur source de cet achat.",
    )
    produit_nom = models.CharField(max_length=255, verbose_name="Produit acheté")
    quantite = models.DecimalField(max_digits=12, decimal_places=2)
    unite = models.CharField(max_length=10, choices=UNITE_CHOICES, default=UNITE_SACS)
    poids_par_sac = models.DecimalField(
        max_digits=8, decimal_places=3,
        null=True, blank=True,
        verbose_name="Poids par sac (kg)",
        help_text="Poids d'un sac en kg. Renseigné si unite='sacs'. "
                  "Garantit la traçabilité et empêche les mélanges de poids.",
    )
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    prix_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # ── Paiement fournisseur ─────────────────────────────────────────────────
    type_paiement = models.CharField(
        max_length=10, choices=TYPE_PAIEMENT_CHOICES, default=TYPE_CASH,
        help_text="Cash = payé immédiatement; Crédit = dette totale; Partiel = acompte.",
    )
    montant_paye_initial = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Acompte versé si type_paiement=partiel.",
    )
    journal_payable = models.ForeignKey(
        "finance.JournalPayable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="achats_mpsl",
        help_text="Journal de dette fournisseur auto-créé si crédit ou partiel. "
                  "Plusieurs achats d'un même bon de commande partagent le même journal.",
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="achats_mpsl_crees",
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Achat MPSL"
        verbose_name_plural = "Achats MPSL"
        ordering = ["-date"]
        constraints = [
            models.CheckConstraint(condition=Q(quantite__gt=0), name="achatmpsl_quantite_positive"),
            models.CheckConstraint(condition=Q(prix_unitaire__gte=0), name="achatmpsl_prix_unitaire_positif"),
            models.CheckConstraint(condition=Q(prix_total__gte=0), name="achatmpsl_prix_total_positif"),
            models.CheckConstraint(
                condition=Q(poids_par_sac__isnull=True) | Q(poids_par_sac__gt=0),
                name="achatmpsl_poids_par_sac_positif",
            ),
            # Règle métier : si achat en sacs, poids_par_sac est obligatoire
            models.CheckConstraint(
                condition=~Q(unite="sacs") | Q(poids_par_sac__isnull=False),
                name="achatmpsl_poids_requis_si_sacs",
            ),
        ]
        indexes = [
            models.Index(fields=["lieu", "date"], name="achatmpsl_lieu_date_idx"),
        ]

    def __str__(self):
        return f"Achat MPSL {self.produit_nom} x {self.quantite} {self.unite} @ {self.lieu}"

    def save(self, *args, **kwargs):
        # Recalcul de prix_total si absent ou nul, quelle que soit la valeur de prix_unitaire.
        # Couvre le cas achat gratuit (prix_unitaire=0) → prix_total=0 correct.
        # Le service enregistrer_achat_mpsl pré-calcule toujours prix_total avant create().
        if self.quantite is not None and self.prix_unitaire is not None:
            if not self.prix_total or self.prix_total == 0:
                self.prix_total = Decimal(str(self.quantite)) * Decimal(str(self.prix_unitaire))
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
        # Recalcul de prix_total si absent ou nul, quelle que soit la valeur de prix_unitaire.
        if self.quantite is not None and self.prix_unitaire is not None:
            if not self.prix_total or self.prix_total == 0:
                self.prix_total = Decimal(str(self.quantite)) * Decimal(str(self.prix_unitaire))
        super().save(*args, **kwargs)
