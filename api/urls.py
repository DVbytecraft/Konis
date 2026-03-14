"""
API REST KONIS : /api/auth/*, /api/boutique/*, /api/admin/*, /api/comptable/*, /api/usine/*
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from api.views.auth_views import LoginView, RefreshView, LogoutView, MeView
from api.views.health_views import HealthView
from api.views.boutique_views import StockBoutiqueViewSet, ProduitBoutiqueViewSet, VenteBoutiqueViewSet, MoutureSeuleView, TicketReprintView
from api.views.admin_views import (
    EntrepriseViewSet,
    FactoryViewSet,
    LieuViewSet,
    LocationByTypeView,
    UserViewSet,
    CategorieViewSet,
    ProduitViewSet,
    StockViewSet,
    TransfertViewSet,
    AchatUsineViewSet as AdminAchatUsineViewSet,
    TicketAdminViewSet,
    CategorieDepenseViewSet,
    DepenseViewSet,
)
from api.views.comptable_views import (
    StockComptableViewSet,
    TransfertComptableViewSet,
    TicketComptableViewSet,
    CategorieDepenseComptableViewSet,
    DepenseComptableViewSet,
    AchatUsineComptableViewSet,
    RapportBoutiquesView,
    RapportUsinesView,
    DetailBoutiqueView,
    DetailUsineView,
    BilanView,
)
from api.views.usine_views import (
    AchatUsineViewSet,
    FactoryDashboardView,
    FactoryFinishedProductsCatalogView,
    FactoryMovementsJournalView,
    FactoryRawMaterialsCatalogView,
    FactoryStockView,
    LotProductionUsineViewSet,
    MoutureSeuleUsineView,
    ProfitByLotReportView,
    ProfitByPeriodReportView,
    RapportBeneficesUsineView,
    StockBoutiquesProduitFiniViewSet,
    TransfertCessionUsineViewSet,
    TransfertInterUsineViewSet,
)
from api.views.facture_views import FactureListCreateView, FactureDetailView

# Auth : pas de router
auth_urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
]

# Boutique
router_boutique = DefaultRouter()
router_boutique.register("stock", StockBoutiqueViewSet, basename="boutique-stock")
router_boutique.register("produits", ProduitBoutiqueViewSet, basename="boutique-produits")
router_boutique.register("ventes", VenteBoutiqueViewSet, basename="boutique-ventes")

# Admin
router_admin = DefaultRouter()
router_admin.register("entreprises", EntrepriseViewSet, basename="admin-entreprises")
router_admin.register("lieux", LieuViewSet, basename="admin-lieux")
router_admin.register("factories", FactoryViewSet, basename="admin-factories")
router_admin.register("users", UserViewSet, basename="admin-users")
router_admin.register("categories", CategorieViewSet, basename="admin-categories")
router_admin.register("produits", ProduitViewSet, basename="admin-produits")
router_admin.register("stocks", StockViewSet, basename="admin-stocks")
router_admin.register("transferts", TransfertViewSet, basename="admin-transferts")
router_admin.register("achats-usine", AdminAchatUsineViewSet, basename="admin-achats-usine")
router_admin.register("tickets", TicketAdminViewSet, basename="admin-tickets")
router_admin.register("categories-depense", CategorieDepenseViewSet, basename="admin-categories-depense")
router_admin.register("depenses", DepenseViewSet, basename="admin-depenses")

# Comptable
router_comptable = DefaultRouter()
router_comptable.register("stocks", StockComptableViewSet, basename="comptable-stocks")
router_comptable.register("transferts", TransfertComptableViewSet, basename="comptable-transferts")
router_comptable.register("ventes", TicketComptableViewSet, basename="comptable-ventes")
router_comptable.register("categories-depense", CategorieDepenseComptableViewSet, basename="comptable-categories-depense")
router_comptable.register("depenses", DepenseComptableViewSet, basename="comptable-depenses")
router_comptable.register("achats-usine", AchatUsineComptableViewSet, basename="comptable-achats-usine")

# Usine
router_usine = DefaultRouter()
router_usine.register("achats", AchatUsineViewSet, basename="usine-achats")
router_usine.register("lots", LotProductionUsineViewSet, basename="usine-lots")
router_usine.register("cessions", TransfertCessionUsineViewSet, basename="usine-cessions")
router_usine.register("stocks-boutiques", StockBoutiquesProduitFiniViewSet, basename="usine-stocks-boutiques")
router_usine.register("transferts-inter-usines", TransfertInterUsineViewSet, basename="usine-transferts-inter-usines")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include((auth_urlpatterns, "auth"))),
    path("locations/by-type/", LocationByTypeView.as_view(), name="locations-by-type"),
    path("boutique/mouture-seule/", MoutureSeuleView.as_view(), name="boutique-mouture-seule"),
    path("boutique/tickets/<int:ticket_id>/reimprimer/", TicketReprintView.as_view(), name="boutique-ticket-reimprimer"),
    path("boutique/", include(router_boutique.urls)),
    path("admin/", include(router_admin.urls)),
    path("comptable/", include(router_comptable.urls)),
    path("usine/", include(router_usine.urls)),
    path("usine/rapports/benefices/", RapportBeneficesUsineView.as_view(), name="usine-rapport-benefices"),
    path("factory/finished-products/catalog/", FactoryFinishedProductsCatalogView.as_view(), name="factory-finished-products-catalog"),
    path("factory/raw-materials/catalog/", FactoryRawMaterialsCatalogView.as_view(), name="factory-raw-materials-catalog"),
    path("factory/movements-journal/", FactoryMovementsJournalView.as_view(), name="factory-movements-journal"),
    path("factory/stock/", FactoryStockView.as_view(), name="factory-stock"),
    path("factory/mouture-seule/", MoutureSeuleUsineView.as_view(), name="factory-mouture-seule"),
    path("factory/dashboard/", FactoryDashboardView.as_view(), name="factory-dashboard"),
    path("reports/profit-by-lot/", ProfitByLotReportView.as_view(), name="reports-profit-by-lot"),
    path("reports/profit-by-period/", ProfitByPeriodReportView.as_view(), name="reports-profit-by-period"),
    path("transfers/", TransfertViewSet.as_view({"get": "list"}), name="transfers-list"),
    path("comptable/rapport-boutiques/", RapportBoutiquesView.as_view(), name="comptable-rapport-boutiques"),
    path("comptable/rapport-boutiques/<int:lieu_id>/", DetailBoutiqueView.as_view(), name="comptable-detail-boutique"),
    path("comptable/rapport-usines/", RapportUsinesView.as_view(), name="comptable-rapport-usines"),
    path("comptable/rapport-usines/<int:lieu_id>/", DetailUsineView.as_view(), name="comptable-detail-usine"),
    path("comptable/bilan/", BilanView.as_view(), name="comptable-bilan"),
    path("factures/", FactureListCreateView.as_view(), name="factures-list-create"),
    path("factures/<int:pk>/", FactureDetailView.as_view(), name="factures-detail"),
]
