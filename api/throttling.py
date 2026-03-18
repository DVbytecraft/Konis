"""
Throttling KONIS : limite login (anti-bruteforce) et création de ventes (anti-abus).
"""
from rest_framework.throttling import SimpleRateThrottle


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
