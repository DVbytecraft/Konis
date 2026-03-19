from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CheckConstraint, Q


class TokenRevocationEpoch(models.Model):
    """
    Époque de révocation globale des tokens JWT.

    Créé automatiquement par `python manage.py full_reset`.
    Tout access token dont le champ `iat` (issued-at) est antérieur ou égal à
    `revoked_before` est rejeté immédiatement par JWTCookieAuthentication,
    même s'il est encore cryptographiquement valide.

    Fonctionnement :
      - full_reset() crée un enregistrement avec revoked_before = now()
      - JWTCookieAuthentication lit le dernier enregistrement à chaque requête
      - Les tokens émis après le reset (iat > revoked_before) sont acceptés
      - Le prochain full_reset nettoie les anciens enregistrements et en crée un nouveau

    Performance : la table est vide en exploitation normale (0 enregistrement).
    La requête `.first()` sur une table vide est instantanée avec l'index pk.
    """
    revoked_before = models.DateTimeField(
        help_text="Tout token JWT émis à ou avant cette date/heure est invalide."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Époque de révocation JWT"
        verbose_name_plural = "Époques de révocation JWT"
        ordering = ["-revoked_before"]

    def __str__(self):
        return f"Révocation avant {self.revoked_before.isoformat()}"


class Entreprise(models.Model):
    """Entreprise (KONIS en V0)."""
    nom = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_primary(cls):
        ent = cls.objects.order_by("id").first()
        if ent is None:
            ent = cls.objects.create(
                nom=getattr(settings, "DEFAULT_ENTREPRISE_NAME", "ENTREPRISE-DEFAULT")
            )
        return ent

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Entreprise"
        verbose_name_plural = "Entreprises"


class Lieu(models.Model):
    """Lieu : usine, magasin (boutique) ou dépôt MPSL."""
    TYPE_USINE = "usine"
    TYPE_MAGASIN = "magasin"
    TYPE_MPSL = "mpsl"
    TYPE_CHOICES = [
        (TYPE_USINE, "Usine"),
        (TYPE_MAGASIN, "Magasin"),
        (TYPE_MPSL, "MPSL"),
    ]

    entreprise = models.ForeignKey(
        Entreprise, on_delete=models.PROTECT, related_name="lieux"
    )
    nom = models.CharField(max_length=255)
    adresse = models.TextField(blank=True, default="")
    code = models.CharField(max_length=20, blank=True, default="", help_text="Code lieu pour numéros ticket (ex: KARA, CENTRE)")
    type_lieu = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    is_active = models.BooleanField(default=True)
    mouture_enabled = models.BooleanField(
        default=True,
        help_text="Ce lieu propose-t-il le service de mouture (broyage de grain) ?"
    )
    prix_mouture_defaut = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Prix mouture par défaut (FCFA/kg)",
        help_text="Pré-rempli automatiquement dans le formulaire de saisie.",
    )
    prix_mouture_max = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Prix mouture maximum autorisé (FCFA/kg)",
        help_text="Si défini, tout prix supérieur est refusé sans autorisation admin.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if getattr(settings, "SINGLE_ENTREPRISE", False):
            primary = Entreprise.get_primary()
            if self.entreprise_id != primary.id:
                self.entreprise = primary
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} ({self.get_type_lieu_display()})"

    class Meta:
        verbose_name = "Lieu"
        verbose_name_plural = "Lieux"
        constraints = [
            CheckConstraint(
                condition=Q(prix_mouture_defaut__isnull=True) | Q(prix_mouture_defaut__gt=0),
                name="lieu_prix_mouture_defaut_positif",
            ),
            CheckConstraint(
                condition=Q(prix_mouture_max__isnull=True) | Q(prix_mouture_max__gt=0),
                name="lieu_prix_mouture_max_positif",
            ),
        ]


class CustomUser(AbstractUser):
    """Utilisateur avec rôle : supreme_admin, admin, daf, comptable, usine, boutique ou mpsl."""
    ROLE_SUPREME_ADMIN = "supreme_admin"
    ROLE_ADMIN = "admin"
    ROLE_DAF = "daf"
    ROLE_COMPTABLE = "comptable"
    ROLE_USINE = "usine"
    ROLE_BOUTIQUE = "boutique"
    ROLE_MPSL = "mpsl"
    ROLE_CHOICES = [
        (ROLE_SUPREME_ADMIN, "Supreme Admin"),
        (ROLE_ADMIN,         "Admin"),
        (ROLE_DAF,           "DAF"),
        (ROLE_COMPTABLE,     "Comptable"),
        (ROLE_USINE,         "Usine"),
        (ROLE_BOUTIQUE,      "Boutique"),
        (ROLE_MPSL,          "MPSL"),
    ]

    entreprise = models.ForeignKey(
        Entreprise, on_delete=models.PROTECT, related_name="utilisateurs", null=True
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_BOUTIQUE, db_index=True)
    lieu = models.OneToOneField(
        Lieu,
        on_delete=models.SET_NULL,  # SET_NULL : suppression d'un Lieu n'entraîne pas la suppression de l'utilisateur
        related_name="compte_boutique",
        null=True,
        blank=True,
        help_text="Pour rôle boutique : le magasin lié à ce compte.",
    )
    tokens_revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Si renseigné, tout token JWT émis AVANT cette date est invalidé. "
            "Mis à jour automatiquement lors d'un changement de mot de passe ou d'une désactivation."
        ),
    )

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def is_factory(self) -> bool:
        """True si l'utilisateur est rattaché à une usine."""
        return bool(self.lieu_id and self.lieu and self.lieu.type_lieu == Lieu.TYPE_USINE)

    def is_mpsl(self) -> bool:
        """True si l'utilisateur est rattaché à un dépôt MPSL."""
        return bool(self.lieu_id and self.lieu and self.lieu.type_lieu == Lieu.TYPE_MPSL)

    def save(self, *args, **kwargs):
        if getattr(settings, "SINGLE_ENTREPRISE", False):
            primary = Entreprise.get_primary()
            if self.entreprise_id != primary.id:
                self.entreprise = primary
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
