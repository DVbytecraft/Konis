"""
API Usine KONIS : achats, productions, transferts vers boutiques.
Isolation stricte par lieu usine.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from api.permissions import IsComptableRole, IsFactoryUser, IsUsineRole
from api.throttling import MoutureCreateRateThrottle, UsineCreateRateThrottle
from api.utils import filter_by_date, filter_by_lieu, get_lieu_usine
from audit.services import audit_log
from api.serializers import (
    AchatUsineCreateSerializer,
    AchatUsineSerializer,
    LotProductionCreateSerializer,
    LotProductionSerializer,
    MoutureSeuleSerializer,
    StockSerializer,
    TicketSerializer,
    TransfertCessionCreateSerializer,
    TransfertCessionSerializer,
    TransfertDirectUsineCreateSerializer,
    TransfertInterUsineCreateSerializer,
    TransfertInterUsineSerializer,
    TransfertSerializer,
)
from core.models import CustomUser, Lieu
from inventaire.models import AchatUsine, Stock
from inventaire.services import ErreurStock, enregistrer_achat_usine
from produits.models import Categorie, Produit
from usine.models import LotProduction, TransfertCession, TransfertInterUsine
from ventes.models import Ticket
from usine.services import creer_lot_production, transferer_lot_vers_boutique, transferer_lot_vers_usine
from ventes.services import vente_mouture_seule


# --- Achats ----------------------------------------------------------------

class AchatUsineViewSet(ModelViewSet):
    """
    GET /api/usine/achats/ : historique des achats d'intrants.
    POST /api/usine/achats/ : enregistrer un achat.
    """
    serializer_class = AchatUsineSerializer
    permission_classes = [IsAuthenticated, IsFactoryUser]
    throttle_classes = [UsineCreateRateThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = AchatUsine.objects.select_related("lieu", "created_by").order_by("-date")
        lieu = get_lieu_usine(self.request)
        if self.request.user.role == CustomUser.ROLE_USINE:
            return qs.filter(lieu=lieu) if lieu else qs.none()
        if lieu:
            return qs.filter(lieu=lieu)
        if not self.request.user.entreprise_id:
            return qs.none()
        return qs.filter(lieu__entreprise_id=self.request.user.entreprise_id)

    def create(self, request, *args, **kwargs):
        data = request.data
        ser = AchatUsineCreateSerializer(data=data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        lieu = d["lieu"]
        if request.user.role == CustomUser.ROLE_USINE and request.user.lieu_id != lieu.id:
            return Response({"detail": "Acces limite a votre usine."}, status=status.HTTP_403_FORBIDDEN)
        try:
            achat = enregistrer_achat_usine(
                lieu=lieu,
                produit_nom=d["produit_nom"],
                quantite=d["quantite"],
                unite=d["unite"],
                prix_unitaire=d.get("prix_unitaire", Decimal("0")),
                notes=d.get("notes", ""),
                created_by=request.user,
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AchatUsineSerializer(achat).data, status=status.HTTP_201_CREATED)


# --- Production -----------------------------------------------------------

class LotProductionUsineViewSet(ModelViewSet):
    """
    GET /api/usine/lots/ : lots de production.
    POST /api/usine/lots/ : creer un nouveau lot.
    """
    serializer_class = LotProductionSerializer
    permission_classes = [IsAuthenticated, IsFactoryUser]
    throttle_classes = [UsineCreateRateThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = LotProduction.objects.select_related("lieu_usine", "produit_fini", "created_by")
        lieu = get_lieu_usine(self.request)
        if self.request.user.role == CustomUser.ROLE_USINE:
            return qs.filter(lieu_usine=lieu) if lieu else qs.none()
        if lieu:
            return qs.filter(lieu_usine=lieu)
        if not self.request.user.entreprise_id:
            return qs.none()
        return qs.filter(lieu_usine__entreprise_id=self.request.user.entreprise_id)

    def create(self, request, *args, **kwargs):
        data = request.data
        ser = LotProductionCreateSerializer(data=data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        lieu_usine = d["lieu_usine"]
        if request.user.role == CustomUser.ROLE_USINE and request.user.lieu_id != lieu_usine.id:
            return Response({"detail": "Acces limite a votre usine."}, status=status.HTTP_403_FORBIDDEN)
        try:
            lot = creer_lot_production(
                lieu_usine=lieu_usine,
                produit_fini=d["produit_fini"],
                nom_lot=d["nom_lot"],
                quantite_sacs=d["quantite_sacs"],
                poids=d.get("poids", Decimal("0")),
                unite_poids=d.get("unite_poids", "kg"),
                created_by=request.user,
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LotProductionSerializer(lot).data, status=status.HTTP_201_CREATED)


# --- Transferts cession ---------------------------------------------------

class TransfertCessionUsineViewSet(ModelViewSet):
    """
    GET /api/usine/cessions/ : historique des transferts vers boutiques.
    POST /api/usine/cessions/ : creer un transfert.
    """
    serializer_class = TransfertCessionSerializer
    permission_classes = [IsAuthenticated, IsFactoryUser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = TransfertCession.objects.select_related(
            "lot__lieu_usine", "lot__produit_fini", "boutique"
        ).order_by("-created_at")
        lieu = get_lieu_usine(self.request)
        if self.request.user.role == CustomUser.ROLE_USINE:
            return qs.filter(lot__lieu_usine=lieu) if lieu else qs.none()
        if lieu:
            return qs.filter(lot__lieu_usine=lieu)
        if not self.request.user.entreprise_id:
            return qs.none()
        return qs.filter(lot__lieu_usine__entreprise_id=self.request.user.entreprise_id)

    def create(self, request, *args, **kwargs):
        data = request.data
        ser = TransfertCessionCreateSerializer(data=data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        lot = d["lot"]
        if request.user.role == CustomUser.ROLE_USINE and request.user.lieu_id != lot.lieu_usine_id:
            return Response({"detail": "Acces limite a votre usine."}, status=status.HTTP_403_FORBIDDEN)
        if lot.lieu_usine.entreprise_id != d["boutique"].entreprise_id:
            return Response(
                {"detail": "Transfert inter-entreprises interdit."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cession = transferer_lot_vers_boutique(
                lot=lot,
                boutique=d["boutique"],
                quantite_sacs=d["quantite_sacs"],
                poids_total=d.get("poids_total", Decimal("0")),
                prix_par_sac=d["prix_par_sac"],
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransfertCessionSerializer(cession).data, status=status.HTTP_201_CREATED)


# --- Transferts inter-usines -----------------------------------------------

class TransfertInterUsineViewSet(ModelViewSet):
    """
    GET /api/usine/transferts-inter-usines/ : historique des transferts vers autres usines.
    POST /api/usine/transferts-inter-usines/ : creer un transfert inter-usines.
    """
    serializer_class = TransfertInterUsineSerializer
    permission_classes = [IsAuthenticated, IsFactoryUser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = TransfertInterUsine.objects.select_related(
            "lot__lieu_usine", "lot__produit_fini", "usine_destination", "created_by"
        ).order_by("-created_at")
        lieu = get_lieu_usine(self.request)
        if self.request.user.role == CustomUser.ROLE_USINE:
            if not lieu:
                return qs.none()
            return qs.filter(lot__lieu_usine=lieu) | qs.filter(usine_destination=lieu)
        if lieu:
            return (qs.filter(lot__lieu_usine=lieu) | qs.filter(usine_destination=lieu)).distinct()
        if not self.request.user.entreprise_id:
            return qs.none()
        return qs.filter(lot__lieu_usine__entreprise_id=self.request.user.entreprise_id)

    def create(self, request, *args, **kwargs):
        data = request.data
        ser = TransfertInterUsineCreateSerializer(data=data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        lot = d["lot"]
        if request.user.role == CustomUser.ROLE_USINE and request.user.lieu_id != lot.lieu_usine_id:
            return Response({"detail": "Acces limite a votre usine."}, status=status.HTTP_403_FORBIDDEN)
        if lot.lieu_usine.entreprise_id != d["usine_destination"].entreprise_id:
            return Response(
                {"detail": "Transfert inter-entreprises interdit."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            inter = transferer_lot_vers_usine(
                lot=lot,
                usine_destination=d["usine_destination"],
                quantite_sacs=d["quantite_sacs"],
                poids_total=d.get("poids_total", Decimal("0")),
                prix_par_sac=d.get("prix_par_sac", Decimal("0")),
                notes=d.get("notes", ""),
                created_by=request.user,
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransfertInterUsineSerializer(inter).data, status=status.HTTP_201_CREATED)


# --- Stock boutiques (vue usine) -----------------------------------------

class StockBoutiquesProduitFiniViewSet(ReadOnlyModelViewSet):
    """GET /api/usine/stocks-boutiques/ : stock produits finis dans les boutiques."""
    serializer_class = StockSerializer
    permission_classes = [IsAuthenticated, IsFactoryUser]

    def get_queryset(self):
        qs = Stock.objects.filter(lieu__type_lieu=Lieu.TYPE_MAGASIN).select_related("produit", "lieu")
        lieu = get_lieu_usine(self.request)
        if not self.request.user.entreprise_id:
            return qs.none()
        qs = qs.filter(lieu__entreprise_id=self.request.user.entreprise_id)
        if self.request.user.role == CustomUser.ROLE_USINE and lieu:
            produits_ids = LotProduction.objects.filter(
                lieu_usine=lieu
            ).values_list("produit_fini_id", flat=True).distinct()
            return qs.filter(
                lieu__entreprise_id=lieu.entreprise_id,
                produit_id__in=produits_ids,
            )
        return qs


# --- Catalogue produits finis ---------------------------------------------

class FactoryFinishedProductsCatalogView(APIView):
    """GET/POST /api/factory/finished-products/catalog/"""
    permission_classes = [IsAuthenticated, IsFactoryUser]

    def get(self, request):
        entreprise = request.user.entreprise
        produits = Produit.objects.filter(
            entreprise=entreprise, category=Produit.CATEGORY_FINISHED
        ).order_by("nom")
        return Response([
            {"id": p.id, "name": p.nom, "code": p.code or "", "unit": p.unite}
            for p in produits
        ])

    def post(self, request):
        entreprise = request.user.entreprise
        data = request.data
        name = (data.get("name") or "").strip()
        code = (data.get("code") or "").strip().upper() or None
        unit = (data.get("unit") or "kg").strip()
        if not name:
            return Response({"detail": "Le nom est requis."}, status=status.HTTP_400_BAD_REQUEST)
        if code and Produit.objects.filter(entreprise=entreprise, code=code).exists():
            return Response({"detail": "Ce code existe deja."}, status=status.HTTP_400_BAD_REQUEST)
        cat, _ = Categorie.objects.get_or_create(nom="Produits finis")
        p = Produit.objects.create(
            entreprise=entreprise, nom=name, code=code, unite=unit,
            categorie=cat, category=Produit.CATEGORY_FINISHED
        )
        return Response(
            {"id": p.id, "name": p.nom, "code": p.code or "", "unit": p.unite},
            status=status.HTTP_201_CREATED,
        )


# --- Dashboard usine ------------------------------------------------------

class FactoryDashboardView(APIView):
    """GET /api/factory/dashboard/"""
    permission_classes = [IsAuthenticated, IsFactoryUser]

    def get(self, request):
        lieu = get_lieu_usine(request)
        # Pour les admins sans lieu specifie, retourner un dashboard vide
        if not lieu:
            if request.user.role == CustomUser.ROLE_ADMIN:
                return Response({
                    "lieu": "Admin (aucune usine sélectionnée)",
                    "stock_usine": [],
                    "total_achats_fcfa": "0",
                    "total_sacs_transferes": "0",
                    "last_productions": [],
                    "last_transfers": [],
                    "last_achats": [],
                })
            return Response({"detail": "Lieu usine introuvable."}, status=status.HTTP_404_NOT_FOUND)

        last_lots = LotProduction.objects.filter(lieu_usine=lieu).select_related("produit_fini").order_by("-created_at")[:5]
        last_cessions = TransfertCession.objects.filter(
            lot__lieu_usine=lieu
        ).select_related("boutique", "lot__produit_fini").order_by("-created_at")[:5]
        last_achats = AchatUsine.objects.filter(lieu=lieu).order_by("-date")[:5]
        stock_usine = Stock.objects.filter(lieu=lieu).select_related("produit")
        total_achats = AchatUsine.objects.filter(lieu=lieu).aggregate(t=Sum("prix_total"))["t"] or 0
        total_sacs = TransfertCession.objects.filter(
            lot__lieu_usine=lieu
        ).aggregate(t=Sum("quantite_sacs"))["t"] or 0

        return Response({
            "lieu": lieu.nom,
            "stock_usine": [
                {"produit": s.produit.nom, "quantite": str(s.quantite), "unite": s.produit.unite}
                for s in stock_usine
            ],
            "total_achats_fcfa": str(total_achats),
            "total_sacs_transferes": str(total_sacs),
            "last_productions": [
                {
                    "id": l.id, "nom_lot": l.nom_lot, "produit": l.produit_fini.nom,
                    "quantite_sacs": str(l.quantite_sacs), "poids": str(l.poids),
                    "unite_poids": l.unite_poids, "created_at": l.created_at.isoformat(),
                }
                for l in last_lots
            ],
            "last_transfers": [
                {
                    "id": c.id, "lot": c.lot.nom_lot, "boutique": c.boutique.nom,
                    "quantite_sacs": str(c.quantite_sacs), "prix_par_sac": str(c.prix_par_sac),
                    "montant": str(c.montant_cession), "created_at": c.created_at.isoformat(),
                }
                for c in last_cessions
            ],
            "last_achats": [
                {
                    "id": a.id, "produit_nom": a.produit_nom, "quantite": str(a.quantite),
                    "unite": a.unite, "prix_total": str(a.prix_total), "date": a.date.isoformat(),
                }
                for a in last_achats
            ],
        })


# --- Rapports comptables --------------------------------------------------

class ProfitByLotReportView(APIView):
    """GET /api/reports/profit-by-lot/"""
    permission_classes = [IsAuthenticated, IsComptableRole]

    def get(self, request):
        _montant_expr = ExpressionWrapper(
            F("cessions__quantite_sacs") * F("cessions__prix_par_sac"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        qs = (
            LotProduction.objects
            .select_related("lieu_usine", "produit_fini")
            .annotate(
                total_cessions_sacs=Sum("cessions__quantite_sacs"),
                total_montant_cessions=Sum(_montant_expr),
            )
        )
        if request.user.role == CustomUser.ROLE_COMPTABLE and request.user.entreprise_id:
            qs = qs.filter(lieu_usine__entreprise_id=request.user.entreprise_id)
        data = [
            {
                "lot_id": lot.id,
                "nom_lot": lot.nom_lot,
                "produit_fini": lot.produit_fini.nom,
                "lieu_usine": lot.lieu_usine.nom,
                "quantite_sacs": str(lot.quantite_sacs),
                "sacs_transferes": str(lot.total_cessions_sacs or Decimal("0")),
                "montant_cessions": str(lot.total_montant_cessions or Decimal("0")),
                "created_at": lot.created_at.isoformat(),
            }
            for lot in qs
        ]
        return Response(data)


class ProfitByPeriodReportView(APIView):
    """GET /api/reports/profit-by-period/"""
    permission_classes = [IsAuthenticated, IsComptableRole]

    def get(self, request):
        qs = (
            TransfertCession.objects.values(
                lieu=F("boutique__nom"),
                produit=F("lot__produit_fini__nom"),
            )
            .annotate(
                total_sacs=Sum("quantite_sacs"),
                montant=Sum(F("quantite_sacs") * F("prix_par_sac")),
            )
            .order_by("lieu", "produit")
        )
        if request.user.role == CustomUser.ROLE_COMPTABLE and request.user.entreprise_id:
            qs = qs.filter(
                lot__lieu_usine__entreprise_id=request.user.entreprise_id,
                boutique__entreprise_id=request.user.entreprise_id,
            )
        return Response(list(qs))


class RapportBeneficesUsineView(APIView):
    """GET /api/usine/rapports/benefices/ (alias)"""
    permission_classes = [IsAuthenticated, IsComptableRole]

    def get(self, request):
        return ProfitByLotReportView().get(request)


# --- Stock usine ----------------------------------------------------------

class FactoryStockView(APIView):
    """GET /api/factory/stock/"""
    permission_classes = [IsAuthenticated, IsFactoryUser]

    def get(self, request):
        lieu = get_lieu_usine(request)
        if not lieu:
            if request.user.role == CustomUser.ROLE_ADMIN:
                return Response([])
            return Response({"detail": "Lieu usine introuvable."}, status=status.HTTP_404_NOT_FOUND)
        stocks = Stock.objects.filter(lieu=lieu).select_related("produit").order_by("produit__nom")
        return Response([
            {
                "produit_id": s.produit_id,
                "produit_nom": s.produit.nom,
                "produit_code": s.produit.code or "",
                "quantite": str(s.quantite),
                "unite": s.produit.unite,
            }
            for s in stocks
        ])


# --- Catalogue matieres premieres -----------------------------------------

class FactoryRawMaterialsCatalogView(APIView):
    """GET/POST /api/factory/raw-materials/catalog/"""
    permission_classes = [IsAuthenticated, IsFactoryUser]

    def get(self, request):
        entreprise = request.user.entreprise
        produits = Produit.objects.filter(
            entreprise=entreprise, category=Produit.CATEGORY_RAW_MATERIAL
        ).order_by("nom")
        return Response([
            {"id": p.id, "name": p.nom, "code": p.code or "", "unit": p.unite}
            for p in produits
        ])

    def post(self, request):
        entreprise = request.user.entreprise
        data = request.data
        name = (data.get("name") or "").strip()
        code = (data.get("code") or "").strip().upper() or None
        unit = (data.get("unit") or "kg").strip()
        if not name:
            return Response({"detail": "Le nom est requis."}, status=status.HTTP_400_BAD_REQUEST)
        if code and Produit.objects.filter(entreprise=entreprise, code=code).exists():
            return Response({"detail": "Ce code existe deja."}, status=status.HTTP_400_BAD_REQUEST)
        cat, _ = Categorie.objects.get_or_create(nom="Matières premières")
        p = Produit.objects.create(
            entreprise=entreprise, nom=name, code=code, unite=unit,
            categorie=cat, category=Produit.CATEGORY_RAW_MATERIAL
        )
        return Response(
            {"id": p.id, "name": p.nom, "code": p.code or "", "unit": p.unite},
            status=status.HTTP_201_CREATED,
        )


# --- Journal des mouvements usine -----------------------------------------

class FactoryMovementsJournalView(APIView):
    """GET /api/factory/movements-journal/"""
    permission_classes = [IsAuthenticated, IsFactoryUser]

    def get(self, request):
        lieu = get_lieu_usine(request)
        if not lieu:
            if request.user.role == CustomUser.ROLE_ADMIN:
                return Response({
                    "entries": [],
                    "exits": [],
                    "totals": {"entries_value": "0", "exits_value": "0", "net_value": "0"},
                })
            return Response({"detail": "Lieu usine introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # Recuperer les mouvements de stock pour l'usine
        from inventaire.models import MouvementStock, Transfert

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        product_id = request.query_params.get("product_id")

        # Entrees: achats et productions
        entries = []
        # Achats
        achats = AchatUsine.objects.filter(lieu=lieu).select_related("created_by")
        for a in achats:
            entries.append({
                "id": f"achat-{a.id}",
                "date": a.date.isoformat(),
                "movement_type": "raw_material_receipt",
                "product_name": a.produit_nom,
                "product_category": "Matière première",
                "quantity": str(a.quantite),
                "unit_price": str(a.prix_unitaire),
                "amount": str(a.prix_total),
                "reference": f"Achat #{a.id}",
            })

        # Productions (stock credite)
        lots = LotProduction.objects.filter(lieu_usine=lieu).select_related("produit_fini", "created_by")
        for lot in lots:
            entries.append({
                "id": f"production-{lot.id}",
                "date": lot.created_at.isoformat(),
                "movement_type": "production_output",
                "product_name": lot.produit_fini.nom,
                "product_category": "Produit fini",
                "quantity": str(lot.quantite_sacs),
                "unit_price": "0",
                "amount": "0",
                "reference": lot.nom_lot,
            })

        # Sorties: transferts vers boutiques
        exits = []
        cessions = TransfertCession.objects.filter(lot__lieu_usine=lieu).select_related("lot__produit_fini", "boutique")
        for c in cessions:
            exits.append({
                "id": f"cession-{c.id}",
                "date": c.created_at.isoformat(),
                "movement_type": "transfer_to_shop",
                "product_name": c.lot.produit_fini.nom,
                "product_category": "Produit fini",
                "quantity": str(c.quantite_sacs),
                "unit_price": str(c.prix_par_sac),
                "amount": str(c.montant_cession),
                "reference": f"{c.lot.nom_lot} → {c.boutique.nom}",
            })

        # Filtrer par date si specifie
        if start_date:
            entries = [e for e in entries if e["date"] >= start_date]
            exits = [e for e in exits if e["date"] >= start_date]
        if end_date:
            entries = [e for e in entries if e["date"] <= end_date]
            exits = [e for e in exits if e["date"] <= end_date]

        # Filtrer par produit si specifie (scoped à l'entreprise du lieu)
        if product_id:
            try:
                produit = Produit.objects.get(pk=product_id, entreprise=lieu.entreprise)
                entries = [e for e in entries if e["product_name"] == produit.nom]
                exits = [e for e in exits if e["product_name"] == produit.nom]
            except Produit.DoesNotExist:
                pass

        # Calculer les totaux
        entries_value = sum(Decimal(e["amount"]) for e in entries)
        exits_value = sum(Decimal(e["amount"]) for e in exits)

        return Response({
            "entries": entries,
            "exits": exits,
            "totals": {
                "entries_value": str(entries_value),
                "exits_value": str(exits_value),
                "net_value": str(entries_value - exits_value),
            },
        })


class MoutureSeuleUsineView(APIView):
    """
    GET  /api/factory/mouture-seule/ : historique mouture du lieu usine.
    POST /api/factory/mouture-seule/ : crée une mouture-seule idempotente.
    """
    permission_classes = [IsAuthenticated, IsUsineRole]
    throttle_classes = [MoutureCreateRateThrottle]

    class _Pagination(PageNumberPagination):
        page_size = 20
        page_size_query_param = "page_size"
        max_page_size = 100

    def get(self, request):
        lieu = get_lieu_usine(request)
        if lieu is None:
            return Response(
                {"detail": "Aucun lieu usine associé à ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = (
            Ticket.objects.filter(lieu=lieu, mouture=True)
            .prefetch_related("lignes__produit")
            .order_by("-date")
        )
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")
        source = (request.query_params.get("source") or "").strip().lower()
        if debut:
            qs = qs.filter(date__date__gte=debut)
        if fin:
            qs = qs.filter(date__date__lte=fin)
        if source in {"seule", "mouture_seule"}:
            qs = qs.annotate(lignes_count=Count("lignes")).filter(lignes_count=0)
        elif source in {"vente", "vente_avec_mouture"}:
            qs = qs.annotate(lignes_count=Count("lignes")).filter(lignes_count__gt=0)

        paginator = self._Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(TicketSerializer(page, many=True).data)

    def post(self, request):
        lieu = get_lieu_usine(request)
        if lieu is None:
            return Response(
                {"detail": "Aucun lieu usine associé à ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not lieu.mouture_enabled:
            return Response(
                {"detail": "Le service de mouture n'est pas activé pour cette usine."},
                status=status.HTTP_403_FORBIDDEN,
        )
        ser = MoutureSeuleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
        if idempotency_key and len(idempotency_key) > 128:
            return Response(
                {"detail": "Header Idempotency-Key trop long (max 128)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        produit_nom = ser.validated_data.get("produit_nom", "")
        produit_ref = None
        produit_id = ser.validated_data.get("produit_id")
        if produit_id:
            try:
                produit_ref = Produit.objects.get(
                    pk=produit_id, entreprise=request.user.entreprise
                )
            except Produit.DoesNotExist:
                return Response(
                    {"detail": f"Produit {produit_id} introuvable ou non autorisé."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            ticket, created = vente_mouture_seule(
                lieu=lieu,
                quantite_apportee=ser.validated_data["quantite_apportee"],
                quantite_achetee=ser.validated_data["quantite_achetee"],
                unite=ser.validated_data["unite"],
                prix_par_kg=ser.validated_data["prix_par_kg"],
                produit_apporte=produit_nom,
                produit_ref=produit_ref,
                idempotency_key=idempotency_key,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if created:
            audit_log(
                user=request.user,
                action="mouture_seule_créée",
                object_type="ticket",
                object_id=ticket.pk,
                extra={"numero": ticket.numero, "montant_total": str(ticket.montant_total), "lieu": lieu.nom},
                request=request,
            )
        else:
            audit_log(
                user=request.user,
                action="mouture_seule_rejouee",
                object_type="ticket",
                object_id=ticket.pk,
                extra={"numero": ticket.numero, "idempotency_key": idempotency_key, "lieu": lieu.nom},
                request=request,
            )
        return Response(
            TicketSerializer(ticket).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# --- Transferts directs usine (sans LotProduction) ----------------------------

class TransfertDirectUsineViewSet(ModelViewSet):
    """
    GET  /api/usine/transferts-directs/ : historique des transferts directs sortants.
    POST /api/usine/transferts-directs/ : créer un transfert direct vers usine ou magasin.
    Pas de LotProduction requis, pas de prix — mouvement pur de stock.
    """
    serializer_class = TransfertSerializer
    permission_classes = [IsAuthenticated, IsFactoryUser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        from inventaire.models import Transfert as TransfertModel
        qs = TransfertModel.objects.select_related(
            "from_lieu", "to_lieu"
        ).prefetch_related("mouvements__produit").filter(
            from_lieu__type_lieu=Lieu.TYPE_USINE,
        ).order_by("-date")
        lieu = get_lieu_usine(self.request)
        if self.request.user.role == CustomUser.ROLE_USINE:
            return qs.filter(from_lieu=lieu) if lieu else qs.none()
        if lieu:
            return (qs.filter(from_lieu=lieu) | qs.filter(to_lieu=lieu)).distinct()
        if not self.request.user.entreprise_id:
            return qs.none()
        return qs.filter(from_lieu__entreprise_id=self.request.user.entreprise_id)

    def create(self, request, *args, **kwargs):
        from inventaire.services import transfert_direct_usine_vers
        ser = TransfertDirectUsineCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        from_lieu = d["from_lieu"]
        to_lieu = d["to_lieu"]

        if request.user.role == CustomUser.ROLE_USINE and request.user.lieu_id != from_lieu.id:
            return Response(
                {"detail": "Acces limite a votre usine."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if from_lieu.entreprise_id != to_lieu.entreprise_id:
            return Response(
                {"detail": "Transfert inter-entreprises interdit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lignes_raw = d["lignes"]
        lignes = []
        for item in lignes_raw:
            produit_id = item.get("produit_id") or item.get("produit")
            try:
                produit = Produit.objects.get(pk=produit_id, entreprise=from_lieu.entreprise)
            except Produit.DoesNotExist:
                return Response(
                    {"detail": f"Produit {produit_id} introuvable dans cette usine."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quantite = Decimal(str(item["quantite"]))
            lignes.append((produit, quantite))

        try:
            transfert = transfert_direct_usine_vers(
                from_usine=from_lieu,
                to_lieu=to_lieu,
                lignes=lignes,
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        audit_log(
            user=request.user,
            action="transfert_direct_usine_cree",
            object_type="transfert",
            object_id=transfert.pk,
            extra={
                "from_lieu": from_lieu.nom,
                "to_lieu": to_lieu.nom,
                "nb_lignes": len(lignes),
            },
            request=request,
        )
        return Response(TransfertSerializer(transfert).data, status=status.HTTP_201_CREATED)
