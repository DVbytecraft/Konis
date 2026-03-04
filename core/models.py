from django.contrib.auth.models import AbstractUser
from django.db import models


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

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Entreprise"
        verbose_name_plural = "Entreprises"


class Lieu(models.Model):
    """Lieu : usine ou magasin (boutique)."""
    TYPE_USINE = "usine"
    TYPE_MAGASIN = "magasin"
    TYPE_CHOICES = [
        (TYPE_USINE, "Usine"),
        (TYPE_MAGASIN, "Magasin"),
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nom} ({self.get_type_lieu_display()})"

    class Meta:
        verbose_name = "Lieu"
        verbose_name_plural = "Lieux"


class CustomUser(AbstractUser):
    """Utilisateur avec rôle : admin, comptable, usine ou boutique."""
    ROLE_ADMIN = "admin"
    ROLE_COMPTABLE = "comptable"
    ROLE_USINE = "usine"
    ROLE_BOUTIQUE = "boutique"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_COMPTABLE, "Comptable"),
        (ROLE_USINE, "Usine"),
        (ROLE_BOUTIQUE, "Boutique"),
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

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def is_factory(self) -> bool:
        """True si l'utilisateur est rattaché à une usine."""
        return bool(self.lieu_id and self.lieu and self.lieu.type_lieu == Lieu.TYPE_USINE)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
