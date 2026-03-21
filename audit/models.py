"""
Modèle d'audit KONIS : trace des actions sensibles (connexion, vente, transfert, dépense).
"""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Log d'audit : utilisateur, action, date, objet concerné."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log d'audit"
        verbose_name_plural = "Logs d'audit"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.user_id} at {self.created_at}"


class AlerteLog(models.Model):
    """
    Historique des alertes émises par check_alerts.

    Permet de suivre les récurrences, filtrer par entreprise/type,
    et éviter de perdre des alertes si le cron rate une exécution.
    """
    NIVEAU_INFO    = "info"
    NIVEAU_WARNING = "warning"
    NIVEAU_ERROR   = "error"
    NIVEAU_CHOICES = [
        (NIVEAU_INFO,    "Info"),
        (NIVEAU_WARNING, "Warning"),
        (NIVEAU_ERROR,   "Error"),
    ]

    code       = models.CharField(max_length=64, db_index=True,
                                  help_text="Ex : STOCK_BAS, PROJET_DEPASSEMENT, TICKETS_SANS_IDEMPOTENCY_KEY")
    niveau     = models.CharField(max_length=10, choices=NIVEAU_CHOICES, default=NIVEAU_WARNING)
    message    = models.TextField()
    extra      = models.JSONField(default=dict, blank=True,
                                  help_text="Données structurées : lieu, produit, montant, etc.")
    entreprise = models.ForeignKey(
        "core.Entreprise",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="alertes",
        help_text="Entreprise concernée (null = alerte globale).",
    )
    resolu     = models.BooleanField(default=False,
                                     help_text="Marquer True une fois l'alerte traitée.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alerte"
        verbose_name_plural = "Alertes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code", "created_at"], name="audit_alerte_code_idx"),
            models.Index(fields=["niveau", "resolu", "created_at"], name="audit_alerte_niveau_idx"),
            models.Index(fields=["entreprise", "created_at"], name="audit_alerte_ent_idx"),
        ]

    def __str__(self):
        return f"[{self.niveau.upper()}] {self.code} — {self.created_at:%Y-%m-%d %H:%M}"
