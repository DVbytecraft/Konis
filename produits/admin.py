from django.contrib import admin
from .models import Categorie, Produit


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "created_at")
    search_fields = ("nom",)


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "categorie", "unite", "updated_at")
    list_filter = ("categorie",)
    search_fields = ("nom", "code")
    autocomplete_fields = ("categorie",)
