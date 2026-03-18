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
