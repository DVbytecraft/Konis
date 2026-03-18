"""
Service d'audit : enregistrement des actions sensibles.
"""
from audit.models import AuditLog


def _get_client_ip(request):
    """Extrait l'IP réelle du client (supporte X-Forwarded-For pour les proxies)."""
    if request is None:
        return None
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def audit_log(user, action, object_type="", object_id=None, extra=None, request=None):
    """Enregistre une entrée d'audit (utilisateur, action, IP, date, objet)."""
    AuditLog.objects.create(
        user=user,
        action=action,
        object_type=object_type or "",
        object_id=object_id,
        extra=extra or {},
        ip_address=_get_client_ip(request),
    )
