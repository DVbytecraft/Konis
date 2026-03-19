"""
Admin Django KONIS : Entreprise, Lieux (usine/boutiques), Utilisateurs.
Permet d'ajouter des boutiques et des comptes boutique depuis /admin/.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CustomUser, Entreprise, Lieu


@admin.register(Entreprise)
class EntrepriseAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "nif", "quitus_fiscal", "created_at")
    search_fields = ("nom", "nif")
    fields = ("nom", "nif", "quitus_fiscal")


@admin.register(Lieu)
class LieuAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "code", "type_lieu", "entreprise", "created_at")
    list_filter = ("type_lieu", "entreprise", "created_at")
    search_fields = ("nom", "code")
    raw_id_fields = ("entreprise",)
    list_editable = ("code",)
    
    fieldsets = (
        ("Informations principales", {
            "fields": ("nom", "code", "type_lieu", "entreprise")
        }),
        ("Dates", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    readonly_fields = ("created_at", "updated_at")
    
    def get_queryset(self, request):
        """Optimiser les requêtes avec select_related."""
        qs = super().get_queryset(request)
        return qs.select_related("entreprise")
    
    def get_form(self, request, obj=None, **kwargs):
        """Pré-remplir le type_lieu avec 'magasin' lors de la création."""
        form = super().get_form(request, obj, **kwargs)
        if obj is None:  # Création d'un nouveau lieu
            form.base_fields['type_lieu'].initial = Lieu.TYPE_MAGASIN
        return form


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "lieu", "entreprise", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")
    raw_id_fields = ("entreprise", "lieu")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profil", {"fields": ("first_name", "last_name", "email")}),
        ("KONIS", {"fields": ("role", "entreprise", "lieu")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2")}),
        ("Profil", {"fields": ("first_name", "last_name", "email")}),
        ("KONIS", {"fields": ("role", "entreprise", "lieu")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
