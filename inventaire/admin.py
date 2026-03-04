from django.contrib import admin

from .models import AchatUsine, MouvementStock, Stock, Transfert


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("produit", "lieu", "quantite")
    list_filter = ("lieu", "produit__categorie")
    search_fields = ("produit__nom", "produit__code", "lieu__nom")
    autocomplete_fields = ("produit", "lieu")


class MouvementStockInline(admin.TabularInline):
    model = MouvementStock
    extra = 1
    autocomplete_fields = ("produit",)


@admin.register(Transfert)
class TransfertAdmin(admin.ModelAdmin):
    list_display = ("from_lieu", "to_lieu", "date")
    list_filter = ("from_lieu", "to_lieu")
    inlines = [MouvementStockInline]
    autocomplete_fields = ("from_lieu", "to_lieu")


@admin.register(AchatUsine)
class AchatUsineAdmin(admin.ModelAdmin):
    list_display = ("produit_nom", "lieu", "quantite", "unite", "prix_total", "date")
    list_filter = ("lieu", "unite")
    search_fields = ("produit_nom", "lieu__nom")
    autocomplete_fields = ("lieu",)
    readonly_fields = ("prix_total",)
