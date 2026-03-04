from django.contrib import admin

from .models import CategorieDepense, Depense


@admin.register(CategorieDepense)
class CategorieDepenseAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "created_at")
    search_fields = ("nom",)


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ("id", "lieu", "categorie", "montant", "date", "libelle")
    list_filter = ("lieu", "categorie", "date")
    search_fields = ("libelle",)
    raw_id_fields = ("lieu", "categorie")
