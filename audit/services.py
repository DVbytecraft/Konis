"""
Service d'audit : enregistrement des actions sensibles.
"""
from django.conf import settings

from audit.models import AuditLog


def _get_client_ip(request):
    """
    Extrait l'IP réelle du client.

    X-Forwarded-For n'est honoré QUE si REMOTE_ADDR figure dans TRUSTED_PROXIES
    (liste définie dans settings.py via la variable d'env TRUSTED_PROXIES).
    Sans proxy de confiance, REMOTE_ADDR est retourné directement pour éviter
    toute usurpation d'IP via le header.
    """
    if request is None:
        return None
    remote_addr = request.META.get("REMOTE_ADDR", "")
    trusted = getattr(settings, "TRUSTED_PROXIES", frozenset())
    if trusted and remote_addr in trusted:
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if x_forwarded:
            # Le premier IP (leftmost) est celui du client tel que vu par le proxy
            return x_forwarded.split(",")[0].strip()
    return remote_addr


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
