"""
Throttling KONIS : limite login (anti-bruteforce) et création de ventes (anti-abus).
"""
from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Limite les tentatives de connexion par IP (ex. 10/min)."""
    scope = "login"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class VenteCreateRateThrottle(SimpleRateThrottle):
    """Limite la création de ventes par utilisateur (ex. 60/min)."""
    scope = "ventes_create"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(request.user.pk),
        }


class MoutureCreateRateThrottle(SimpleRateThrottle):
    """Limite la creation des tickets mouture par utilisateur."""
    scope = "mouture_create"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(request.user.pk),
        }
