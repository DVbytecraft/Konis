"""
Permissions strictes par role KONIS : admin, comptable, boutique.
"""
from rest_framework import permissions

from core.models import CustomUser


class IsAdminRole(permissions.BasePermission):
    """Acces reserve au role admin."""
    message = "Reserve aux administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == CustomUser.ROLE_ADMIN
        )


class IsComptableRole(permissions.BasePermission):
    """Acces reserve au role comptable (ou admin)."""
    message = "Reserve aux comptables ou administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in (CustomUser.ROLE_COMPTABLE, CustomUser.ROLE_ADMIN)
        )


class IsBoutiqueRole(permissions.BasePermission):
    """Acces reserve strictement au role boutique."""
    message = "Reserve aux boutiques."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == CustomUser.ROLE_BOUTIQUE
        )


class IsUsineRole(permissions.BasePermission):
    """Acces reserve au role usine (ou admin)."""
    message = "Reserve aux usines ou administrateurs."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in (CustomUser.ROLE_USINE, CustomUser.ROLE_ADMIN)
        )


class IsFactoryUser(permissions.BasePermission):
    """Acces reserve aux utilisateurs rattaches a une usine ou aux administrateurs."""
    message = "Reserve aux utilisateurs d'usine ou administrateurs."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Les administrateurs ont toujours acces
        if request.user.role == CustomUser.ROLE_ADMIN:
            return True
        # Les utilisateurs usine doivent etre rattaches a une usine
        return request.user.is_factory()


class IsBoutiqueOwnLieu(permissions.BasePermission):
    """
    Pour role boutique : uniquement les donnees du lieu de l'utilisateur.
    Admin : tous les lieux (filtres cote vue si besoin).
    """
    message = "Acces limite au lieu de votre boutique."

    def has_object_permission(self, request, view, obj):
        if request.user.role != CustomUser.ROLE_BOUTIQUE:
            return False
        lieu = getattr(obj, "lieu", None) or getattr(obj, "to_lieu", None) or getattr(obj, "from_lieu", None)
        if lieu is None:
            return True
        return request.user.lieu_id == lieu.id


# Aliases pour la checklist securite (noms explicites)
IsAdminUser = IsAdminRole
IsComptableUser = IsComptableRole
IsBoutiqueUser = IsBoutiqueRole
IsUsineUser = IsUsineRole
