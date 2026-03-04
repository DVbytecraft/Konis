"""
Service d'audit : enregistrement des actions sensibles.
"""
from audit.models import AuditLog


def audit_log(user, action, object_type="", object_id=None, extra=None):
    """Enregistre une entrée d'audit (utilisateur, action, date, objet)."""
    AuditLog.objects.create(
        user=user,
        action=action,
        object_type=object_type or "",
        object_id=object_id,
        extra=extra or {},
    )
