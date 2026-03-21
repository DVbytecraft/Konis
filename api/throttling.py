"""
Throttling KONIS : limite login (anti-bruteforce) et création de ventes (anti-abus).

Chaque throttle logue un WARNING via konis.alerts quand la limite est atteinte,
permettant une surveillance centralisée sans dépendance externe.
"""
import logging

from rest_framework.throttling import SimpleRateThrottle

_alert = logging.getLogger("konis.alerts")


class LoginRateThrottle(SimpleRateThrottle):
    """Limite les tentatives de connexion par IP pour les utilisateurs non authentifiés."""
    scope = "login"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if not allowed:
            _alert.warning("THROTTLE_429 scope=login ip=%s", self.get_ident(request))
        return allowed


class LoginIPRateThrottle(SimpleRateThrottle):
    """
    Throttle global par IP sur le login — s'applique TOUJOURS, même si déjà authentifié.
    Bloque les attaques multi-comptes depuis une même IP (brute-force distribué par username).
    Complète LoginRateThrottle qui ne s'applique qu'aux non-authentifiés.
    """
    scope = "login_ip"

    def get_cache_key(self, request, view):
        # Toujours par IP, sans exception pour les authentifiés
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

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if not allowed:
            user_id = getattr(getattr(request, "user", None), "pk", "?")
            _alert.warning("THROTTLE_429 scope=ventes_create user_id=%s path=%s", user_id, request.path)
        return allowed


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


class FactureCreateRateThrottle(SimpleRateThrottle):
    """Limite la création de factures par utilisateur (anti-abus)."""
    scope = "facture_create"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(request.user.pk),
        }


class UsineCreateRateThrottle(SimpleRateThrottle):
    """Limite la création de lots/achats usine par utilisateur."""
    scope = "usine_create"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(request.user.pk),
        }


class FinanceCreateRateThrottle(SimpleRateThrottle):
    """Limite les opérations de création finance (journaux, paiements, emprunts) par utilisateur."""
    scope = "finance_create"

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(request.user.pk),
        }


class RefreshRateThrottle(SimpleRateThrottle):
    """
    Rate limit strict sur /auth/refresh — s'applique TOUJOURS par IP,
    même si l'utilisateur est authentifié (access_token valide en cache).
    Empêche le spam de refresh avec un token volé.
    """
    scope = "refresh"

    def get_cache_key(self, request, view):
        # Jamais d'exemption — toujours par IP
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
