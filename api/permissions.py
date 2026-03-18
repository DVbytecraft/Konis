"""
Permissions strictes par role KONIS.

Hiérarchie des rôles :
  supreme_admin > admin > daf > comptable > usine / boutique / mpsl

  - supreme_admin : accès total, supervise tout
  - admin         : accès opérationnel complet (supervisé par supreme_admin)
  - daf           : accès financier complet, pas de gestion utilisateurs
  - comptable     : lecture financière + dépenses
  - usine         : opérations usine
  - boutique      : opérations boutique
  - mpsl          : opérations dépôt MPSL

Règle générale : supreme_admin est inclus dans TOUTES les permissions admin/daf/opérationnel.
"""
from rest_framework import permissions

from core.models import CustomUser

# Rôles avec accès admin opérationnel complet
_ADMIN_ROLES = (CustomUser.ROLE_SUPREME_ADMIN, CustomUser.ROLE_ADMIN)

# Rôles avec accès financier complet (DAF + admins + comptable)
_FINANCE_ROLES = (CustomUser.ROLE_SUPREME_ADMIN, CustomUser.ROLE_ADMIN, CustomUser.ROLE_DAF, CustomUser.ROLE_COMPTABLE)

# Rôles avec accès financier en lecture (comptable + DAF + admins)
_FINANCE_READ_ROLES = (CustomUser.ROLE_SUPREME_ADMIN, CustomUser.ROLE_ADMIN, CustomUser.ROLE_DAF, CustomUser.ROLE_COMPTABLE)


class IsSupremeAdminRole(permissions.BasePermission):
    """Accès réservé exclusivement au supreme_admin."""
    message = "Réservé au Supreme Admin."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == CustomUser.ROLE_SUPREME_ADMIN
        )


class IsAdminRole(permissions.BasePermission):
    """Accès réservé aux admins (admin + supreme_admin)."""
    message = "Réservé aux administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in _ADMIN_ROLES
        )


class IsDafRole(permissions.BasePermission):
    """Accès réservé au DAF et aux admins (accès financier complet)."""
    message = "Réservé au DAF ou aux administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in _FINANCE_ROLES
        )


class IsComptableRole(permissions.BasePermission):
    """Accès réservé au comptable, DAF et admins."""
    message = "Réservé aux comptables ou administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in _FINANCE_READ_ROLES
        )


class IsBoutiqueRole(permissions.BasePermission):
    """Accès réservé strictement au role boutique."""
    message = "Réservé aux boutiques."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == CustomUser.ROLE_BOUTIQUE
        )


class IsUsineRole(permissions.BasePermission):
    """Accès réservé au role usine ou admins."""
    message = "Réservé aux usines ou administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in (CustomUser.ROLE_USINE, *_ADMIN_ROLES)
        )


class IsFactoryUser(permissions.BasePermission):
    """Accès réservé aux utilisateurs rattachés à une usine ou aux admins."""
    message = "Réservé aux utilisateurs d'usine ou administrateurs."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in _ADMIN_ROLES:
            return True
        return request.user.is_factory()


class IsBoutiqueOwnLieu(permissions.BasePermission):
    """
    Pour role boutique : uniquement les données du lieu de l'utilisateur.
    Admin : tous les lieux (filtres côté vue si besoin).
    """
    message = "Accès limité au lieu de votre boutique."

    def has_object_permission(self, request, view, obj):
        if request.user.role != CustomUser.ROLE_BOUTIQUE:
            return False
        lieu = getattr(obj, "lieu", None) or getattr(obj, "to_lieu", None) or getattr(obj, "from_lieu", None)
        if lieu is None:
            return True
        return request.user.lieu_id == lieu.id


class IsMPSLRole(permissions.BasePermission):
    """Accès réservé au role MPSL ou admins."""
    message = "Réservé aux opérateurs MPSL ou administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in (CustomUser.ROLE_MPSL, *_ADMIN_ROLES)
        )


# Aliases pour la checklist sécurité (noms explicites)
IsAdminUser     = IsAdminRole
IsComptableUser = IsComptableRole
IsBoutiqueUser  = IsBoutiqueRole
IsUsineUser     = IsUsineRole
IsMPSLUser      = IsMPSLRole
IsDafUser       = IsDafRole
