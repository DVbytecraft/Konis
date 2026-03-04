from django.contrib import admin

from ventes.models import Facture, LigneFacture, LigneVente, Ticket


class LigneVenteInline(admin.TabularInline):
    model = LigneVente
    extra = 0


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "numero", "lieu", "date")
    list_filter = ("lieu", "date")
    search_fields = ("numero", "lieu__nom")
    inlines = [LigneVenteInline]


class LigneFactureInline(admin.TabularInline):
    model = LigneFacture
    extra = 0


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ("id", "numero", "lieu", "source_role", "date", "total")
    list_filter = ("source_role", "lieu", "date")
    search_fields = ("numero", "client_nom", "lieu__nom")
    inlines = [LigneFactureInline]
