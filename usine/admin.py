from django.contrib import admin

from usine.models import LotProduction, TransfertCession


@admin.register(LotProduction)
class LotProductionAdmin(admin.ModelAdmin):
    list_display = ("nom_lot", "lieu_usine", "produit_fini", "quantite_sacs", "poids", "unite_poids", "created_at")
    list_filter = ("lieu_usine", "produit_fini")
    search_fields = ("nom_lot", "produit_fini__nom")


@admin.register(TransfertCession)
class TransfertCessionAdmin(admin.ModelAdmin):
    list_display = ("lot", "boutique", "quantite_sacs", "prix_par_sac", "created_at")
    list_filter = ("boutique", "lot__lieu_usine")
    search_fields = ("lot__nom_lot", "boutique__nom")
