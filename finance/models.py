"""
Module Finance KONIS — Gestion financière complète.

Couvre :
  - Créanciers & journaux payables (dettes envers fournisseurs/partenaires)
  - Clients finance & journaux de créances (dettes clients)
  - Emprunts bancaires & remboursements
  - Caisse suprême (trésorerie centrale)
  - Projets & dépenses/dépôts de projets

Règles d'intégrité :
  - Aucun enregistrement financier ne peut être supprimé (on_delete=PROTECT)
  - Un journal soldé est verrouillé (locked_at non null)
  - montant_restant est calculé dynamiquement (montant_initial - montant_paye)
  - Tous les montants : Decimal(14, 2) avec min_value >= 0
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import CheckConstraint, Q

from core.models import CustomUser, Entreprise
from produits.models import Produit


# ─── Constantes partagées ────────────────────────────────────────────────────

STATUT_JOURNAL = [
    ("en_cours", "En cours"),
    ("solde",    "Soldé"),
]

MODE_PAIEMENT = [
    ("especes",  "Espèces"),
    ("cheque",   "Chèque"),
    ("virement", "Virement"),
    ("mobile",   "Mobile Money"),
    ("autre",    "Autre"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# PAYABLES — Dettes envers créanciers
# ═══════════════════════════════════════════════════════════════════════════════

class Creancier(models.Model):
    """Fournisseur, banque ou partenaire à qui l'entreprise doit de l'argent."""

    TYPE_CHOICES = [
        ("fournisseur", "Fournisseur"),
        ("banque",      "Banque"),
        ("partenaire",  "Partenaire"),
        ("autre",       "Autre"),
    ]

    entreprise     = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name="creanciers")
    nom            = models.CharField(max_length=255)
    type_creancier = models.CharField(max_length=20, choices=TYPE_CHOICES, default="fournisseur")
    contact        = models.CharField(max_length=255, blank=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Créancier"
        verbose_name_plural = "Créanciers"
        ordering            = ["nom"]
        indexes             = [models.Index(fields=["entreprise", "nom"], name="creancier_ent_nom_idx")]

    def __str__(self):
        return f"{self.nom} ({self.get_type_creancier_display()})"


class JournalPayable(models.Model):
    """
    Journal de dette envers un créancier.
    Chaque dette distincte = un journal distinct.
    Un journal soldé est verrouillé (locked_at non null).
    """

    creancier       = models.ForeignKey(Creancier, on_delete=models.PROTECT, related_name="journaux")
    reference       = models.CharField(max_length=100, blank=True, help_text="Référence facture fournisseur")
    description     = models.TextField()
    montant_initial = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    montant_paye    = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    statut          = models.CharField(max_length=10, choices=STATUT_JOURNAL, default="en_cours")
    date_echeance   = models.DateField(null=True, blank=True)
    notes           = models.TextField(blank=True)
    created_by      = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at      = models.DateTimeField(auto_now_add=True)
    locked_at       = models.DateTimeField(null=True, blank=True, help_text="Date de verrouillage (soldé)")

    class Meta:
        verbose_name        = "Journal payable"
        verbose_name_plural = "Journaux payables"
        ordering            = ["-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant_initial__gte=Decimal("0.01")), name="jpayable_montant_initial_min"),
            CheckConstraint(condition=Q(montant_paye__gte=0), name="jpayable_montant_paye_non_negatif"),
        ]
        indexes             = [
            models.Index(fields=["creancier", "statut"],       name="jpayable_creancier_statut_idx"),
            models.Index(fields=["statut", "date_echeance"],   name="jpayable_statut_echeance_idx"),
        ]

    @property
    def montant_restant(self) -> Decimal:
        return self.montant_initial - self.montant_paye

    @property
    def est_solde(self) -> bool:
        return self.statut == "solde"

    def __str__(self):
        return f"[{self.get_statut_display()}] {self.creancier.nom} — {self.montant_initial} FCFA"


class PaiementPayable(models.Model):
    """Paiement effectué sur un journal payable."""

    journal       = models.ForeignKey(JournalPayable, on_delete=models.PROTECT, related_name="paiements")
    montant       = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    date          = models.DateField()
    mode_paiement = models.CharField(max_length=10, choices=MODE_PAIEMENT, default="especes")
    reference     = models.CharField(max_length=255, blank=True)
    notes         = models.TextField(blank=True)
    created_by    = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Paiement payable"
        verbose_name_plural = "Paiements payables"
        ordering            = ["-date", "-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant__gte=Decimal("0.01")), name="paiement_payable_montant_min"),
        ]
        indexes             = [
            models.Index(fields=["journal", "date"], name="paiement_payable_jrn_date_idx"),
        ]

    def __str__(self):
        return f"{self.montant} FCFA — {self.journal.creancier.nom} ({self.date})"


# ═══════════════════════════════════════════════════════════════════════════════
# CRÉANCES — Dettes de clients envers l'entreprise
# ═══════════════════════════════════════════════════════════════════════════════

class ClientFinance(models.Model):
    """Client pouvant avoir des dettes envers l'entreprise (créances)."""

    entreprise = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name="clients_finance")
    nom        = models.CharField(max_length=255)
    contact    = models.CharField(max_length=255, blank=True)
    notes      = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Client (finance)"
        verbose_name_plural = "Clients (finance)"
        ordering            = ["nom"]
        indexes             = [models.Index(fields=["entreprise", "nom"], name="clientfin_ent_nom_idx")]

    def __str__(self):
        return self.nom


class JournalCreance(models.Model):
    """
    Journal de créance client.
    Chaque vente à crédit = un journal distinct.
    Un journal soldé est verrouillé.
    """

    client          = models.ForeignKey(ClientFinance, on_delete=models.PROTECT, related_name="journaux")
    reference       = models.CharField(max_length=100, blank=True)
    description     = models.TextField()
    montant_initial = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    montant_paye    = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    statut          = models.CharField(max_length=10, choices=STATUT_JOURNAL, default="en_cours")
    date_echeance   = models.DateField(null=True, blank=True)
    notes           = models.TextField(blank=True)
    created_by      = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at      = models.DateTimeField(auto_now_add=True)
    locked_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "Journal de créance"
        verbose_name_plural = "Journaux de créances"
        ordering            = ["-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant_initial__gte=Decimal("0.01")), name="jcreance_montant_initial_min"),
            CheckConstraint(condition=Q(montant_paye__gte=0), name="jcreance_montant_paye_non_negatif"),
        ]
        indexes             = [
            models.Index(fields=["client", "statut"],         name="jcreance_client_statut_idx"),
            models.Index(fields=["statut", "date_echeance"],  name="jcreance_statut_echeance_idx"),
        ]

    @property
    def montant_restant(self) -> Decimal:
        return self.montant_initial - self.montant_paye

    @property
    def est_solde(self) -> bool:
        return self.statut == "solde"

    def __str__(self):
        return f"[{self.get_statut_display()}] {self.client.nom} — {self.montant_initial} FCFA"


class LigneCreance(models.Model):
    """Ligne détaillée d'un journal de créance (produit ou description libre)."""

    journal       = models.ForeignKey(JournalCreance, on_delete=models.PROTECT, related_name="lignes")
    produit       = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    description   = models.CharField(max_length=500)
    quantite      = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    prix_unitaire = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name        = "Ligne de créance"
        verbose_name_plural = "Lignes de créances"
        constraints         = [
            CheckConstraint(condition=Q(quantite__gt=0), name="lignecreance_quantite_positive"),
            CheckConstraint(condition=Q(prix_unitaire__gte=0), name="lignecreance_prix_non_negatif"),
        ]

    @property
    def total(self) -> Decimal:
        return self.quantite * self.prix_unitaire

    def __str__(self):
        return f"{self.description} × {self.quantite} @ {self.prix_unitaire}"


class PaiementCreance(models.Model):
    """Paiement reçu d'un client sur un journal de créance."""

    journal       = models.ForeignKey(JournalCreance, on_delete=models.PROTECT, related_name="paiements")
    montant       = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    date          = models.DateField()
    mode_paiement = models.CharField(max_length=10, choices=MODE_PAIEMENT, default="especes")
    reference     = models.CharField(max_length=255, blank=True)
    notes         = models.TextField(blank=True)
    created_by    = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Paiement créance"
        verbose_name_plural = "Paiements créances"
        ordering            = ["-date", "-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant__gte=Decimal("0.01")), name="paiement_creance_montant_min"),
        ]
        indexes             = [
            models.Index(fields=["journal", "date"], name="paiement_creance_jrn_date_idx"),
        ]

    def __str__(self):
        return f"{self.montant} FCFA reçu — {self.journal.client.nom} ({self.date})"


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRUNTS — Prêts bancaires
# ═══════════════════════════════════════════════════════════════════════════════

class Emprunt(models.Model):
    """Prêt bancaire reçu par l'entreprise."""

    STATUT_CHOICES = [
        ("en_cours",  "En cours"),
        ("rembourse", "Remboursé"),
    ]

    entreprise        = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name="emprunts")
    nom               = models.CharField(max_length=255, help_text="Nom ou objet du prêt")
    banque            = models.CharField(max_length=255)
    montant_initial   = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    montant_rembourse = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    taux_interet      = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Taux annuel en % (0–100)",
    )
    date_debut        = models.DateField()
    date_echeance     = models.DateField(null=True, blank=True)
    statut            = models.CharField(max_length=10, choices=STATUT_CHOICES, default="en_cours")
    notes             = models.TextField(blank=True)
    created_by        = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at        = models.DateTimeField(auto_now_add=True)
    locked_at         = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "Emprunt"
        verbose_name_plural = "Emprunts"
        ordering            = ["-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant_initial__gte=Decimal("0.01")), name="emprunt_montant_initial_min"),
            CheckConstraint(condition=Q(montant_rembourse__gte=0), name="emprunt_montant_rembourse_non_negatif"),
            CheckConstraint(
                condition=Q(taux_interet__isnull=True) | Q(taux_interet__gte=0),
                name="emprunt_taux_non_negatif",
            ),
            CheckConstraint(
                condition=Q(taux_interet__isnull=True) | Q(taux_interet__lte=100),
                name="emprunt_taux_max_100",
            ),
        ]
        indexes             = [
            models.Index(fields=["entreprise", "statut"], name="emprunt_ent_statut_idx"),
        ]

    @property
    def montant_restant(self) -> Decimal:
        return self.montant_initial - self.montant_rembourse

    @property
    def est_rembourse(self) -> bool:
        return self.statut == "rembourse"

    def __str__(self):
        return f"{self.nom} — {self.banque} ({self.montant_initial} FCFA)"


class RemboursementEmprunt(models.Model):
    """Remboursement d'une échéance d'emprunt."""

    emprunt    = models.ForeignKey(Emprunt, on_delete=models.PROTECT, related_name="remboursements")
    montant    = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    date       = models.DateField()
    reference  = models.CharField(max_length=255, blank=True)
    notes      = models.TextField(blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Remboursement d'emprunt"
        verbose_name_plural = "Remboursements d'emprunts"
        ordering            = ["-date", "-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant__gte=Decimal("0.01")), name="remboursement_montant_min"),
        ]
        indexes             = [
            models.Index(fields=["emprunt", "date"], name="remboursement_emprunt_date_idx"),
        ]

    def __str__(self):
        return f"{self.montant} FCFA — {self.emprunt.nom} ({self.date})"


# ═══════════════════════════════════════════════════════════════════════════════
# CAISSE SUPRÊME — Trésorerie centrale
# ═══════════════════════════════════════════════════════════════════════════════

class CaisseSupremeTransaction(models.Model):
    """
    Mouvement de la caisse centrale (compte bancaire officiel).
    Source unique de vérité financière de l'entreprise.
    """

    TYPE_CHOICES = [
        ("depot",   "Dépôt"),
        ("retrait", "Retrait"),
    ]

    entreprise       = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name="caisse_transactions")
    type_transaction = models.CharField(max_length=10, choices=TYPE_CHOICES)
    montant          = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description      = models.CharField(max_length=500)
    reference        = models.CharField(max_length=255, blank=True)
    date             = models.DateField()
    created_by       = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Transaction caisse suprême"
        verbose_name_plural = "Transactions caisse suprême"
        ordering            = ["-date", "-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant__gte=Decimal("0.01")), name="caisse_montant_min"),
        ]
        indexes             = [
            models.Index(fields=["entreprise", "date"],             name="caisse_ent_date_idx"),
            models.Index(fields=["entreprise", "type_transaction"], name="caisse_ent_type_idx"),
        ]

    def __str__(self):
        return f"{self.get_type_transaction_display()} {self.montant} FCFA ({self.date})"


# ═══════════════════════════════════════════════════════════════════════════════
# PROJETS — Budget et suivi de projets
# ═══════════════════════════════════════════════════════════════════════════════

class Projet(models.Model):
    """Projet avec budget dédié et suivi des dépenses/dépôts."""

    STATUT_CHOICES = [
        ("en_cours", "En cours"),
        ("termine",  "Terminé"),
        ("suspendu", "Suspendu"),
    ]

    entreprise     = models.ForeignKey(Entreprise, on_delete=models.PROTECT, related_name="projets")
    nom            = models.CharField(max_length=255)
    description    = models.TextField(blank=True)
    budget_initial = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    statut         = models.CharField(max_length=10, choices=STATUT_CHOICES, default="en_cours")
    date_debut     = models.DateField()
    date_fin       = models.DateField(null=True, blank=True)
    created_by     = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Projet"
        verbose_name_plural = "Projets"
        ordering            = ["-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(budget_initial__gte=Decimal("0.01")), name="projet_budget_initial_positif"),
        ]
        indexes             = [
            models.Index(fields=["entreprise", "statut"], name="projet_ent_statut_idx"),
        ]

    def __str__(self):
        return f"{self.nom} [{self.get_statut_display()}]"


class DepenseProjet(models.Model):
    """Dépense effectuée sur un projet."""

    projet     = models.ForeignKey(Projet, on_delete=models.PROTECT, related_name="depenses")
    montant    = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description = models.CharField(max_length=500)
    date        = models.DateField()
    created_by  = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Dépense projet"
        verbose_name_plural = "Dépenses projets"
        ordering            = ["-date", "-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant__gte=Decimal("0.01")), name="depense_projet_montant_min"),
        ]
        indexes             = [
            models.Index(fields=["projet", "date"], name="depense_projet_date_idx"),
        ]

    def __str__(self):
        return f"{self.montant} FCFA — {self.projet.nom} ({self.date})"


class DepotProjet(models.Model):
    """Fonds supplémentaires reçus pour financer un projet (après budget initial)."""

    projet      = models.ForeignKey(Projet, on_delete=models.PROTECT, related_name="depots")
    montant     = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description = models.CharField(max_length=500)
    date        = models.DateField()
    created_by  = models.ForeignKey(CustomUser, on_delete=models.PROTECT, related_name="+")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Dépôt projet"
        verbose_name_plural = "Dépôts projets"
        ordering            = ["-date", "-created_at"]
        constraints         = [
            CheckConstraint(condition=Q(montant__gte=Decimal("0.01")), name="depot_projet_montant_min"),
        ]
        indexes             = [
            models.Index(fields=["projet", "date"], name="depot_projet_date_idx"),
        ]

    def __str__(self):
        return f"Dépôt {self.montant} FCFA — {self.projet.nom} ({self.date})"
