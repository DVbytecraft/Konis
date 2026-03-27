"""
API Boutique : stock (mon lieu), produits, ventes (créer / lister).
Filtre strict par lieu = request.user.lieu (rôle boutique).

Règles d'accès :
  - Produits : lecture seule pour boutique (création via usine uniquement)
  - Stock : lecture seule pour boutique (alimentation via cessions usine uniquement)
  - Ventes : création + lecture pour boutique et admin
"""
import csv
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet

from audit.services import audit_log
from api.pagination import KonisPagination
from api.permissions import IsAdminRole, IsBoutiqueRole, IsComptableRole
from api.throttling import MoutureCreateRateThrottle, VenteCreateRateThrottle
from api.utils import get_lieu_boutique
from api.serializers import (
    BoutiqueStockReceiptSerializer,
    MoutureSeuleSerializer,
    ProduitMinimalSerializer,
    StockSerializer,
    TicketReprintCreateSerializer,
    TicketSerializer,
    VenteBoutiqueCreateSerializer,
)
from core.models import CustomUser, Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Produit
from ventes.models import Ticket, TicketReprint
from ventes.services import (
    charger_client_vente,
    normaliser_quantite_en_kg,
    preparer_lignes_vente,
    preparer_mouture_vente,
    valider_prix_mouture,
    vente_boutique,
    vente_mouture_seule,
)


class StockBoutiqueViewSet(ModelViewSet):
    """
    GET  /api/boutique/stock/ : stock du lieu (boutique et admin).
    POST /api/boutique/stock/ : entrée manuelle réservée aux admins uniquement.
    Les boutiques reçoivent du stock exclusivement via les cessions usine.
    """
    serializer_class = StockSerializer
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = None  # retourne tout le stock (liste finie, utilisée pour autocomplete)

    def get_queryset(self):
        lieu = get_lieu_boutique(self.request)
        if not lieu:
            return Stock.objects.none()
        return Stock.objects.filter(lieu=lieu).select_related("produit", "lieu")

    def create(self, request, *args, **kwargs):
        """Réservé aux admins (admin + supreme_admin) — les boutiques ne peuvent pas entrer du stock directement."""
        if request.user.role not in (CustomUser.ROLE_ADMIN, CustomUser.ROLE_SUPREME_ADMIN):
            return Response(
                {"detail": "L'entrée directe de stock est réservée aux administrateurs. "
                           "Le stock boutique est alimenté uniquement via les cessions usine."},
                status=status.HTTP_403_FORBIDDEN,
            )
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Boutique non associée à un lieu."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = BoutiqueStockReceiptSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        produit = ser.validated_data["produit"]
        quantite = ser.validated_data["quantity"]

        with transaction.atomic():
            stock, _ = Stock.objects.get_or_create(
                produit=produit,
                lieu=lieu,
                defaults={"quantite": Decimal("0")},
            )
            stock = Stock.objects.select_for_update().get(pk=stock.pk)
            stock.quantite += quantite
            stock.save(update_fields=["quantite", "updated_at"])

        audit_log(
            user=request.user,
            action="boutique_stock_entree_admin",
            object_type="stock",
            object_id=stock.pk,
            extra={"lieu_id": lieu.pk, "produit_id": produit.pk, "quantite": str(quantite)},
            request=request,
        )
        return Response(StockSerializer(stock).data, status=status.HTTP_201_CREATED)


class ProduitBoutiqueViewSet(ReadOnlyModelViewSet):
    """
    GET /api/boutique/produits/ : produits disponibles au lieu (lecture seule).
    Les produits sont créés et gérés depuis l'usine uniquement.
    """
    serializer_class = ProduitMinimalSerializer
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get_queryset(self):
        """Retourne les produits ayant un enregistrement de stock au lieu de la boutique."""
        lieu = get_lieu_boutique(self.request)
        if not lieu:
            return Produit.objects.none()
        return (
            Produit.objects.filter(stocks__lieu=lieu)
            .select_related("categorie")
            .distinct()
        )


class VenteBoutiqueViewSet(ModelViewSet):
    """
    GET  /api/boutique/ventes/ : tickets du lieu (filtres date optionnels).
    POST /api/boutique/ventes/ : créer une vente (ticket + lignes + mouture optionnelle).

    Filtres GET : ?debut=YYYY-MM-DD&fin=YYYY-MM-DD
    """
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]
    throttle_classes = [VenteCreateRateThrottle]
    pagination_class = KonisPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        lieu = get_lieu_boutique(self.request)
        if not lieu:
            return Ticket.objects.none()
        qs = (
            Ticket.objects.filter(lieu=lieu)
            .prefetch_related("lignes__produit")
            .order_by("-date")
        )
        debut = self.request.query_params.get("debut")
        fin = self.request.query_params.get("fin")
        mouture = self.request.query_params.get("mouture")
        if debut:
            try:
                from datetime import datetime as _dt
                _dt.strptime(debut, "%Y-%m-%d")
            except ValueError:
                raise DRFValidationError({"debut": f"Format de date invalide : '{debut}'. Attendu : YYYY-MM-DD."})
            qs = qs.filter(date__date__gte=debut)
        if fin:
            try:
                from datetime import datetime as _dt
                _dt.strptime(fin, "%Y-%m-%d")
            except ValueError:
                raise DRFValidationError({"fin": f"Format de date invalide : '{fin}'. Attendu : YYYY-MM-DD."})
            qs = qs.filter(date__date__lte=fin)
        if mouture is not None:
            value = mouture.strip().lower() in {"1", "true", "yes", "oui"}
            qs = qs.filter(mouture=value)
        return qs

    def create(self, request, *args, **kwargs):
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Lieu requis (boutique : votre magasin ; admin : fournir ?lieu= ou body lieu)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = VenteBoutiqueCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        mouture = ser.validated_data.get("mouture", False)
        prix_mouture_kg = ser.validated_data.get("prix_mouture_kg")

        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None
        if not idempotency_key:
            from django.conf import settings
            if settings.IDEMPOTENCY_STRICT_MODE:
                return Response({"detail": "Idempotency-Key requis."}, status=status.HTTP_400_BAD_REQUEST)

        # ── Préparation métier (produits, mouture, client) ───────────────────
        try:
            lignes = preparer_lignes_vente(lieu, ser.validated_data["lignes"])
            if mouture:
                valider_prix_mouture(lieu, prix_mouture_kg)
            quantite_apportee_client_kg = preparer_mouture_vente(lieu, ser.validated_data) if mouture else Decimal("0")
            client = charger_client_vente(lieu, ser.validated_data.get("client_id"))
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # ── Enregistrement ───────────────────────────────────────────────────
        try:
            ticket, created = vente_boutique(
                lieu,
                lignes,
                mouture=mouture,
                prix_mouture_kg=prix_mouture_kg,
                quantite_apportee_client_kg=quantite_apportee_client_kg,
                idempotency_key=idempotency_key,
                type_vente=ser.validated_data.get("type_vente", "cash"),
                montant_cash=ser.validated_data.get("montant_cash"),
                client=client,
                created_by=request.user,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not created:
            return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)

        # Auto-upgrade prospect → client dès le premier achat (atomique : WHERE statut=prospect)
        if client and client.statut == client.STATUT_PROSPECT:
            from django.utils import timezone as _tz
            from finance.models import ClientFinance as _CF
            _CF.objects.filter(
                pk=client.pk, statut=_CF.STATUT_PROSPECT
            ).update(statut=_CF.STATUT_CLIENT, updated_at=_tz.now())

        mouture_extra = {}
        if mouture:
            mouture_extra = {
                "prix_mouture_kg": str(prix_mouture_kg) if prix_mouture_kg else None,
                "quantite_apportee_client_kg": str(quantite_apportee_client_kg),
                "cout_mouture": str(ticket.cout_mouture),
            }
        audit_log(
            user=request.user,
            action="vente_creée",
            object_type="ticket",
            object_id=ticket.pk,
            extra={
                "numero": ticket.numero,
                "lieu_id": lieu.pk,
                "mouture": mouture,
                "type_vente": ticket.type_vente,
                "montant_total": str(ticket.montant_total),
                "montant_cash": str(ticket.montant_cash),
                "montant_credit": str(ticket.montant_credit),
                "client_id": ticket.client_id,
                "operateur": request.user.username,
                **mouture_extra,
            },
            request=request,
        )
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class MoutureSeuleView(APIView):
    """
    GET  /api/boutique/mouture-seule/ : historique mouture du lieu.
    POST /api/boutique/mouture-seule/ : crée une mouture-seule idempotente.
    """

    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]
    throttle_classes = [MoutureCreateRateThrottle]

    class _Pagination(PageNumberPagination):
        page_size = 20
        page_size_query_param = "page_size"
        max_page_size = 100

    def get(self, request):
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Lieu requis (boutique : votre magasin ; admin : fournir ?lieu=)."},
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
            try:
                from datetime import datetime as _dt
                _dt.strptime(debut, "%Y-%m-%d")
            except ValueError:
                raise DRFValidationError({"debut": f"Format de date invalide : '{debut}'. Attendu : YYYY-MM-DD."})
            qs = qs.filter(date__date__gte=debut)
        if fin:
            try:
                from datetime import datetime as _dt
                _dt.strptime(fin, "%Y-%m-%d")
            except ValueError:
                raise DRFValidationError({"fin": f"Format de date invalide : '{fin}'. Attendu : YYYY-MM-DD."})
            qs = qs.filter(date__date__lte=fin)
        if source in {"seule", "mouture_seule"}:
            qs = qs.annotate(lignes_count=Count("lignes")).filter(lignes_count=0)
        elif source in {"vente", "vente_avec_mouture"}:
            qs = qs.annotate(lignes_count=Count("lignes")).filter(lignes_count__gt=0)

        paginator = self._Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(TicketSerializer(page, many=True).data)

    def post(self, request):
        lieu = get_lieu_boutique(request)
        if lieu is None:
            return Response(
                {"detail": "Aucun lieu boutique associé à ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not lieu.mouture_enabled:
            return Response(
                {"detail": "Le service de mouture n'est pas activé pour cette boutique."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ser = MoutureSeuleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None
        if not idempotency_key:
            from django.conf import settings
            if settings.IDEMPOTENCY_STRICT_MODE:
                return Response(
                    {"detail": "Idempotency-Key requis."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Garde-fou prix ──────────────────────────────────────────────────
        prix_par_kg = ser.validated_data["prix_par_kg"]
        if lieu.prix_mouture_max and prix_par_kg > lieu.prix_mouture_max:
            return Response(
                {
                    "detail": (
                        f"Prix {prix_par_kg} FCFA/kg dépasse le plafond autorisé "
                        f"({lieu.prix_mouture_max} FCFA/kg). Contactez l'administrateur."
                    )
                },
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
                prix_par_kg=prix_par_kg,
                produit_apporte=produit_nom,
                produit_ref=produit_ref,
                idempotency_key=idempotency_key,
                nombre_sacs=ser.validated_data.get("nombre_sacs"),
                poids_par_sac=ser.validated_data.get("poids_par_sac"),
                type_mouture=Ticket.TYPE_MOUTURE_CLIENT,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if created:
            audit_log(
                user=request.user,
                action="mouture_seule_créée",
                object_type="ticket",
                object_id=ticket.pk,
                extra={
                    "numero": ticket.numero,
                    "montant_total": str(ticket.montant_total),
                    "prix_par_kg": str(prix_par_kg),
                    "quantite_apportee": str(ser.validated_data.get("quantite_apportee", 0)),
                    "quantite_achetee": str(ser.validated_data.get("quantite_achetee", 0)),
                    "unite": ser.validated_data.get("unite", "kg"),
                    "produit_apporte": produit_nom,
                    "lieu_id": lieu.pk,
                    "operateur": request.user.username,
                },
                request=request,
            )
        else:
            audit_log(
                user=request.user,
                action="mouture_seule_rejouee",
                object_type="ticket",
                object_id=ticket.pk,
                extra={
                    "numero": ticket.numero,
                    "idempotency_key": idempotency_key,
                    "operateur": request.user.username,
                },
                request=request,
            )

        return Response(
            TicketSerializer(ticket).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TicketReprintView(APIView):
    """
    POST /api/boutique/tickets/{ticket_id}/reimprimer/
    Enregistre une réimpression de ticket (traçabilité) et retourne les données complètes du ticket.
    Accès : boutique (son propre lieu) + admin.
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]
    throttle_classes   = [VenteCreateRateThrottle]

    def post(self, request, ticket_id):
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Lieu boutique requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.shortcuts import get_object_or_404
        ticket = get_object_or_404(
            Ticket.objects.prefetch_related("lignes__produit").select_related("lieu"),
            pk=ticket_id,
            lieu=lieu,
        )
        ser = TicketReprintCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        TicketReprint.objects.create(
            ticket=ticket,
            utilisateur=request.user,
            boutique=lieu,
            motif=ser.validated_data.get("motif", ""),
        )
        audit_log(
            user=request.user,
            action="ticket_réimprimé",
            object_type="ticket",
            object_id=ticket.pk,
            extra={"numero": ticket.numero, "lieu_id": lieu.pk},
            request=request,
        )
        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)


class MoutureStatsView(APIView):
    """
    GET /api/boutique/mouture-stats/
    Statistiques mouture du lieu : KPI fixes + période personnalisée optionnelle.

    Params optionnels :
      ?debut=YYYY-MM-DD   période personnalisée — début
      ?fin=YYYY-MM-DD     période personnalisée — fin
      ?source=seule|vente filtre type mouture (s'applique à la période perso seulement)
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get(self, request):
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response({"detail": "Lieu requis."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.now().date()

        def _stats(debut, fin, source_filter=None):
            qs = Ticket.objects.filter(
                lieu=lieu, mouture=True,
                date__date__gte=debut, date__date__lte=fin,
            )
            if source_filter in {"seule", "mouture_seule"}:
                qs = qs.annotate(_lc=Count("lignes")).filter(_lc=0)
            elif source_filter in {"vente", "vente_avec_mouture"}:
                qs = qs.annotate(_lc=Count("lignes")).filter(_lc__gt=0)
            agg = qs.aggregate(
                nb_tickets=Count("id"),
                cout_total=Sum("cout_mouture"),
                kg_apportee=Sum("quantite_apportee_client"),
            )
            return {
                "nb_tickets": agg["nb_tickets"] or 0,
                "cout_total": str(agg["cout_total"] or "0.00"),
                "kg_apportee": str(agg["kg_apportee"] or "0.000"),
            }

        # Période personnalisée
        debut_str = request.query_params.get("debut")
        fin_str = request.query_params.get("fin")
        source = (request.query_params.get("source") or "").strip().lower() or None
        custom = None
        if debut_str or fin_str:
            from datetime import date as date_type
            try:
                d = date_type.fromisoformat(debut_str) if debut_str else today - timedelta(days=29)
                f = date_type.fromisoformat(fin_str) if fin_str else today
            except ValueError:
                return Response({"detail": "Format date invalide (YYYY-MM-DD)."}, status=status.HTTP_400_BAD_REQUEST)
            custom = {**_stats(d, f, source), "debut": str(d), "fin": str(f)}

        payload = {
            "aujourd_hui": _stats(today, today),
            "7_jours": _stats(today - timedelta(days=6), today),
            "30_jours": _stats(today - timedelta(days=29), today),
            "prix_defaut": str(lieu.prix_mouture_defaut) if lieu.prix_mouture_defaut else None,
            "prix_max": str(lieu.prix_mouture_max) if lieu.prix_mouture_max else None,
        }
        if custom is not None:
            payload["custom"] = custom
        return Response(payload)


class MoutureExportView(APIView):
    """
    GET /api/boutique/mouture-export/
    Export CSV de l'historique mouture du lieu.

    Paramètres :
      ?debut=YYYY-MM-DD   date de début (défaut : 30 derniers jours)
      ?fin=YYYY-MM-DD     date de fin   (défaut : aujourd'hui)
      ?source=seule|vente filtre par type (optionnel)

    Colonnes CSV :
      Date, Ticket, Lieu, Type, Grain, Apporté(kg), Achet&#233;(kg), Total(kg),
      Prix/kg (FCFA), Coût mouture (FCFA), Montant total (FCFA)
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get(self, request):
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response({"detail": "Lieu requis."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.now().date()
        debut_str = request.query_params.get("debut")
        fin_str = request.query_params.get("fin")
        try:
            from datetime import date
            debut = date.fromisoformat(debut_str) if debut_str else today - timedelta(days=29)
            fin = date.fromisoformat(fin_str) if fin_str else today
        except ValueError:
            return Response({"detail": "Format date invalide (YYYY-MM-DD)."}, status=status.HTTP_400_BAD_REQUEST)

        qs = (
            Ticket.objects.filter(lieu=lieu, mouture=True, date__date__gte=debut, date__date__lte=fin)
            .annotate(lignes_count=Count("lignes"))
            .order_by("date")
        )
        source = (request.query_params.get("source") or "").strip().lower()
        if source in {"seule", "mouture_seule"}:
            qs = qs.filter(lignes_count=0)
        elif source in {"vente", "vente_avec_mouture"}:
            qs = qs.filter(lignes_count__gt=0)

        audit_log(
            user=request.user,
            action="mouture_export_csv",
            object_type="lieu",
            object_id=lieu.pk,
            extra={"lieu": lieu.nom, "debut": str(debut), "fin": str(fin), "source": source},
            request=request,
        )

        filename = f"mouture_{lieu.nom.replace(' ', '_')}_{debut}_{fin}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        # BOM UTF-8 pour compatibilité Excel
        response.write("\ufeff")

        writer = csv.writer(response, delimiter=";")
        writer.writerow([
            "Date", "Ticket", "Lieu", "Type", "Grain",
            "Apporté (kg)", "Acheté (kg)", "Total (kg)",
            "Prix/kg (FCFA)", "Coût mouture (FCFA)", "Montant total (FCFA)",
        ])

        for ticket in qs:
            apportee_kg = float(ticket.quantite_apportee_client or 0)
            prix_kg = float(ticket.prix_mouture_kg or 0)
            cout = float(ticket.cout_mouture or 0)
            total_kg = (cout / prix_kg) if prix_kg > 0 else apportee_kg
            achetee_kg = max(0.0, total_kg - apportee_kg)
            t_type = (
                "Mouture seule" if ticket.lignes_count == 0 else "Vente + mouture"
            )
            writer.writerow([
                ticket.date.strftime("%d/%m/%Y %H:%M"),
                ticket.numero,
                lieu.nom,
                t_type,
                ticket.produit_apporte or "",
                f"{apportee_kg:.3f}",
                f"{achetee_kg:.3f}",
                f"{total_kg:.3f}",
                f"{prix_kg:.2f}",
                f"{cout:.2f}",
                f"{float(ticket.montant_total):.2f}",
            ])

        return response


class MouturePdfExportView(APIView):
    """
    GET /api/boutique/mouture-pdf/
    Rapport PDF mouture : en-tête, résumé, tableau détaillé.

    Params : ?debut=YYYY-MM-DD&fin=YYYY-MM-DD&source=seule|vente
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get(self, request):
        from datetime import date as date_type
        import io
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image as RLImage
        from core.branding import KONIS_BRAND

        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response({"detail": "Lieu requis."}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.now().date()
        debut_str = request.query_params.get("debut")
        fin_str = request.query_params.get("fin")
        try:
            debut = date_type.fromisoformat(debut_str) if debut_str else today - timedelta(days=29)
            fin = date_type.fromisoformat(fin_str) if fin_str else today
        except ValueError:
            return Response({"detail": "Format date invalide (YYYY-MM-DD)."}, status=status.HTTP_400_BAD_REQUEST)

        qs = (
            Ticket.objects.filter(lieu=lieu, mouture=True, date__date__gte=debut, date__date__lte=fin)
            .annotate(lignes_count=Count("lignes"))
            .order_by("date")
        )
        source = (request.query_params.get("source") or "").strip().lower()
        if source in {"seule", "mouture_seule"}:
            qs = qs.filter(lignes_count=0)
        elif source in {"vente", "vente_avec_mouture"}:
            qs = qs.filter(lignes_count__gt=0)

        tickets = list(qs)
        total_cout = sum(float(t.cout_mouture or 0) for t in tickets)
        total_kg = sum(float(t.quantite_apportee_client or 0) for t in tickets)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=15 * mm, rightMargin=15 * mm,
            topMargin=18 * mm, bottomMargin=18 * mm,
            title=f"Rapport Mouture — {lieu.nom}",
        )
        styles = getSampleStyleSheet()
        GREEN = colors.HexColor("#16a34a")
        LIGHT_GREEN = colors.HexColor("#dcfce7")
        GREY_HEADER = colors.HexColor("#f3f4f6")
        DARK = colors.HexColor("#111827")

        title_style = ParagraphStyle("title", parent=styles["Heading1"], textColor=GREEN, fontSize=16, spaceAfter=4)
        sub_style = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.HexColor("#6b7280"), fontSize=9)
        label_style = ParagraphStyle("label", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#374151"))
        value_style = ParagraphStyle("value", parent=styles["Normal"], fontSize=14, textColor=DARK, fontName="Helvetica-Bold")

        period_label = f"{debut.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}"
        source_label = {"seule": "Mouture seule", "vente": "Vente + mouture", "": "Tous types"}.get(source, "Tous types")

        logo_path = (KONIS_BRAND.get("logo_path") or "").strip()
        story = []
        if logo_path:
            try:
                story.append(RLImage(logo_path, width=28 * mm, height=28 * mm, kind="proportional"))
                story.append(Spacer(1, 2 * mm))
            except Exception:
                pass
        story += [
            Paragraph("AGRO KONIS — Service Mouture", title_style),
            Paragraph(f"{lieu.nom} | {period_label} | {source_label}", sub_style),
            Spacer(1, 4 * mm),
            HRFlowable(width="100%", thickness=1, color=GREEN),
            Spacer(1, 4 * mm),
        ]

        # ── Résumé KPI ──
        kpi_data = [
            [
                Paragraph("Tickets", label_style),
                Paragraph("Revenus mouture", label_style),
                Paragraph("Grain client apporté", label_style),
            ],
            [
                Paragraph(str(len(tickets)), value_style),
                Paragraph(f"{total_cout:,.0f} FCFA", value_style),
                Paragraph(f"{total_kg:,.3f} kg", value_style),
            ],
        ]
        kpi_table = Table(kpi_data, colWidths=["33%", "33%", "34%"])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREY_HEADER),
            ("BACKGROUND", (0, 1), (-1, 1), LIGHT_GREEN),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 6 * mm))

        if not tickets:
            story.append(Paragraph("Aucune opération de mouture sur cette période.", sub_style))
        else:
            # ── Tableau détaillé ──
            col_style = ParagraphStyle("col", parent=styles["Normal"], fontSize=7.5, textColor=DARK)
            hdr_style = ParagraphStyle("hdr", parent=styles["Normal"], fontSize=7.5, textColor=colors.white, fontName="Helvetica-Bold")

            headers = ["Date", "Ticket", "Type", "Grain", "Apporté\n(kg)", "Acheté\n(kg)", "Total\n(kg)", "Prix/kg\n(FCFA)", "Coût\n(FCFA)", "Montant\n(FCFA)"]
            rows = [[Paragraph(h, hdr_style) for h in headers]]

            for t in tickets:
                apportee = float(t.quantite_apportee_client or 0)
                prix = float(t.prix_mouture_kg or 0)
                cout = float(t.cout_mouture or 0)
                total_moudre = (cout / prix) if prix > 0 else apportee
                achetee = max(0.0, total_moudre - apportee)
                t_type = "Mouture seule" if t.lignes_count == 0 else "Vente+mouture"
                rows.append([
                    Paragraph(t.date.strftime("%d/%m/%y\n%H:%M"), col_style),
                    Paragraph(t.numero.split("-")[-1] if "-" in t.numero else t.numero, col_style),
                    Paragraph(t_type, col_style),
                    Paragraph(t.produit_apporte or "—", col_style),
                    Paragraph(f"{apportee:.2f}", col_style),
                    Paragraph(f"{achetee:.2f}", col_style),
                    Paragraph(f"{total_moudre:.2f}", col_style),
                    Paragraph(f"{prix:.0f}", col_style),
                    Paragraph(f"{cout:,.0f}", col_style),
                    Paragraph(f"{float(t.montant_total):,.0f}", col_style),
                ])

            # Ligne total
            total_row_style = ParagraphStyle("tot", parent=styles["Normal"], fontSize=7.5, textColor=GREEN, fontName="Helvetica-Bold")
            rows.append([
                Paragraph("TOTAL", total_row_style), Paragraph("", col_style),
                Paragraph("", col_style), Paragraph("", col_style),
                Paragraph(f"{total_kg:.2f}", total_row_style), Paragraph("", col_style),
                Paragraph("", col_style), Paragraph("", col_style),
                Paragraph(f"{total_cout:,.0f}", total_row_style),
                Paragraph(f"{total_cout:,.0f}", total_row_style),
            ])

            page_w = A4[0] - 30 * mm
            col_w = [22 * mm, 22 * mm, 22 * mm, 28 * mm, 16 * mm, 16 * mm, 16 * mm, 18 * mm, 22 * mm, 22 * mm]
            detail_table = Table(rows, colWidths=col_w, repeatRows=1)
            detail_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREEN),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, GREY_HEADER]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, GREEN),
            ]))
            story.append(detail_table)

        # Footer
        story.append(Spacer(1, 8 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"Généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')} — KONIS v2",
            sub_style,
        ))

        doc.build(story)
        buf.seek(0)

        audit_log(
            user=request.user,
            action="mouture_export_pdf",
            object_type="lieu",
            object_id=lieu.pk,
            extra={"lieu": lieu.nom, "debut": str(debut), "fin": str(fin), "source": source, "nb_tickets": len(tickets)},
            request=request,
        )

        fname = f"mouture_{lieu.nom.replace(' ', '_')}_{debut}_{fin}.pdf"
        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        return response


class DashboardBoutiqueView(APIView):
    """
    GET /api/boutique/dashboard/
    Résumé financier du lieu (ventes, cash, créances, dépenses, stock).
    Boutique : son propre lieu. Admin/DAF : ?lieu_id= requis.
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get(self, request):
        from finance.services import get_dashboard_boutique

        if request.user.role in (
            CustomUser.ROLE_BOUTIQUE,
        ):
            lieu = get_lieu_boutique(request)
            if not lieu:
                return Response({"detail": "Lieu introuvable."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Admin/DAF : lieu_id obligatoire pour cibler une boutique spécifique
            lieu_id = request.query_params.get("lieu_id")
            if not lieu_id:
                return Response(
                    {"detail": "Paramètre lieu_id requis (admin/DAF)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                lieu = Lieu.objects.get(
                    pk=lieu_id,
                    entreprise_id=request.user.entreprise_id,
                    type_lieu=Lieu.TYPE_MAGASIN,
                )
            except Lieu.DoesNotExist:
                return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)

        from datetime import datetime
        date_debut = None
        date_fin = None
        raw_debut = request.query_params.get("date_debut")
        raw_fin = request.query_params.get("date_fin")
        for raw, name in ((raw_debut, "date_debut"), (raw_fin, "date_fin")):
            if raw:
                try:
                    datetime.strptime(raw, "%Y-%m-%d")
                except ValueError:
                    return Response(
                        {"detail": f"Format invalide pour {name} : attendu YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        date_debut = raw_debut
        date_fin = raw_fin

        data = get_dashboard_boutique(lieu, date_debut=date_debut, date_fin=date_fin)
        # Convertir Decimal → str pour JSON. None → null (pas str "None"). int/dict/list passent tels quels.
        return Response({k: (str(v) if v is not None and not isinstance(v, (int, dict, list)) else v) for k, v in data.items()})


# ─── Conversion sacs → kg ─────────────────────────────────────────────────────

class ConvertirSacEnKgView(APIView):
    """
    POST /api/boutique/stock/<produit_id>/convertir/
    Convertit N sacs entiers en kg pour le stock de la boutique.
    Body : { "nombre_sacs": <int> }
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def post(self, request, produit_id):
        from inventaire.services import convertir_sac_en_kg
        from decimal import InvalidOperation
        from api.idempotency import IdempotencyGuard

        guard = IdempotencyGuard(request, "conversion_sac_en_kg")
        early = guard.check()
        if early is not None:
            return early

        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            stock = Stock.objects.get(produit_id=produit_id, lieu=lieu)
        except Stock.DoesNotExist:
            return Response({"detail": "Stock introuvable."}, status=status.HTTP_404_NOT_FOUND)

        nombre_sacs = request.data.get("nombre_sacs")
        try:
            nombre_sacs = int(nombre_sacs)
        except (TypeError, ValueError):
            return Response({"detail": "nombre_sacs doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)

        poids_par_sac_override = None
        pps_raw = request.data.get("poids_par_sac")
        if pps_raw is not None:
            try:
                poids_par_sac_override = Decimal(str(pps_raw))
                if poids_par_sac_override <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                return Response({"detail": "poids_par_sac doit être un nombre positif."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            kg = convertir_sac_en_kg(
                stock=stock,
                nombre_sacs=nombre_sacs,
                updated_by=request.user,
                poids_par_sac_override=poids_par_sac_override,
                log_request=request,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        stock.refresh_from_db()
        resp_data = {
            "kg_generes": str(kg),
            "quantite_sacs": str(stock.quantite),
            "quantite_kg": str(stock.quantite_kg),
        }
        guard.success(resp_data)
        return Response(resp_data)


# ─── Conversion kg → sacs ─────────────────────────────────────────────────────

class ConvertirKgEnSacBoutiqueView(APIView):
    """
    POST /api/boutique/stock/<produit_id>/convertir-kg-en-sac/
    Convertit kg en sacs entiers pour le stock de la boutique.
    Body : { "nombre_sacs": <int>, "poids_par_sac": "<decimal>" }
    poids_par_sac est OBLIGATOIRE — jamais deviné.
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def post(self, request, produit_id):
        from inventaire.services import convertir_kg_en_sac
        from decimal import InvalidOperation
        from api.idempotency import IdempotencyGuard

        guard = IdempotencyGuard(request, "conversion_kg_en_sac")
        early = guard.check()
        if early is not None:
            return early

        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            stock = Stock.objects.get(produit_id=produit_id, lieu=lieu)
        except Stock.DoesNotExist:
            return Response({"detail": "Stock introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # nombre_sacs — obligatoire, entier >= 1
        nombre_sacs = request.data.get("nombre_sacs")
        try:
            nombre_sacs = int(nombre_sacs)
            if nombre_sacs <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"detail": "nombre_sacs doit être un entier >= 1."}, status=status.HTTP_400_BAD_REQUEST)

        # poids_par_sac — OBLIGATOIRE, strictement validé
        pps_raw = request.data.get("poids_par_sac")
        if pps_raw is None:
            return Response({"detail": "poids_par_sac est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            poids_par_sac = Decimal(str(pps_raw))
            if poids_par_sac <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            return Response({"detail": "poids_par_sac doit être un nombre > 0."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = convertir_kg_en_sac(
                stock=stock,
                nombre_sacs=nombre_sacs,
                poids_par_sac=poids_par_sac,
                updated_by=request.user,
                idempotency_key=request.headers.get("Idempotency-Key"),
                log_request=request,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        stock.refresh_from_db()
        resp_data = {
            "sacs_crees":    result["sacs_crees"],
            "kg_debites":    str(result["kg_debites"]),
            "quantite_sacs": str(stock.quantite),
            "quantite_kg":   str(stock.quantite_kg),
        }
        guard.success(resp_data)
        return Response(resp_data)


# ─── Clients (lecture seule pour la caisse) ───────────────────────────────────

class ClientsBoutiqueView(APIView):
    """
    GET  /api/boutique/clients/?search=... — recherche clients (scoped entreprise)
    POST /api/boutique/clients/            — créer un nouveau client
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole | IsComptableRole]

    def get(self, request):
        from django.db.models import Count, Max, Q, Sum
        from finance.models import ClientFinance
        from api.serializers_finance import ClientFinanceSerializer

        ent_id = request.user.entreprise_id
        if not ent_id:
            return Response([])

        qs = ClientFinance.objects.filter(entreprise_id=ent_id).order_by("nom")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(nom__icontains=search) | Q(contact__icontains=search))
            return Response(ClientFinanceSerializer(qs[:20], many=True).data)

        # Liste complète avec stats par boutique
        lieu = get_lieu_boutique(request)
        if lieu:
            ticket_filter = Q(tickets__lieu=lieu)
            qs = qs.annotate(
                nb_achats=Count("tickets", filter=ticket_filter, distinct=True),
                dernier_achat=Max("tickets__date", filter=ticket_filter),
                total_achats=Sum("tickets__montant_total", filter=ticket_filter),
            )
        else:
            qs = qs.annotate(
                nb_achats=Count("tickets", distinct=True),
                dernier_achat=Max("tickets__date"),
                total_achats=Sum("tickets__montant_total"),
            )

        data = []
        for c in qs:
            row = ClientFinanceSerializer(c).data
            row["nb_achats"] = getattr(c, "nb_achats", 0) or 0
            row["dernier_achat"] = str(getattr(c, "dernier_achat", None) or "") or None
            row["total_achats"] = str(getattr(c, "total_achats", None) or "0")
            data.append(row)
        return Response(data)

    def post(self, request):
        from finance.models import ClientFinance
        from api.serializers_finance import ClientFinanceSerializer

        ent_id = request.user.entreprise_id
        if not ent_id:
            return Response({"detail": "Entreprise non définie."}, status=400)

        nom = str(request.data.get("nom", "")).strip()
        if not nom:
            return Response({"detail": "Le nom du client est requis."}, status=400)

        # Retourner le client existant si même nom (insensible à la casse)
        existing = ClientFinance.objects.filter(entreprise_id=ent_id, nom__iexact=nom).first()
        if existing:
            return Response(ClientFinanceSerializer(existing).data, status=200)

        statut = str(request.data.get("statut", ClientFinance.STATUT_PROSPECT)).strip()
        if statut not in (ClientFinance.STATUT_PROSPECT, ClientFinance.STATUT_CLIENT):
            statut = ClientFinance.STATUT_PROSPECT

        lieu = get_lieu_boutique(request)
        client = ClientFinance.objects.create(
            entreprise_id=ent_id,
            lieu=lieu,
            nom=nom,
            contact=str(request.data.get("contact", "")).strip(),
            interet=str(request.data.get("interet", "")).strip(),
            notes=str(request.data.get("notes", "")).strip(),
            statut=statut,
        )
        audit_log(
            user=request.user,
            action="client_finance_create",
            object_type="ClientFinance",
            object_id=client.pk,
            extra={"nom": client.nom, "statut": statut},
            request=request,
        )
        return Response(ClientFinanceSerializer(client).data, status=201)


# ─── Créances boutique ────────────────────────────────────────────────────────

class CreanceBoutiqueViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    GET  /api/boutique/creances/               — créances de cette boutique
    GET  /api/boutique/creances/{id}/          — détail + paiements
    POST /api/boutique/creances/{id}/paiement/ — enregistrer un paiement reçu

    Filtre : ?statut=en_cours|solde
    Sécurité : scoping strict par lieu=boutique du user (IDOR impossible).
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get_queryset(self):
        from finance.models import JournalCreance
        lieu = get_lieu_boutique(self.request)
        if not lieu:
            return JournalCreance.objects.none()
        qs = (
            JournalCreance.objects
            .filter(lieu=lieu)
            .select_related("client")
            .prefetch_related("paiements__created_by")
            .order_by("-created_at")
        )
        statut = self.request.query_params.get("statut")
        if statut in ("en_cours", "solde"):
            qs = qs.filter(statut=statut)
        return qs

    def get_serializer_class(self):
        from api.serializers_finance import JournalCreanceSerializer
        return JournalCreanceSerializer

    @action(detail=True, methods=["post"])
    def paiement(self, request, pk=None):
        from finance.models import JournalCreance
        from api.serializers_finance import JournalCreanceSerializer, PaiementCreanceCreateSerializer
        from finance.services import enregistrer_paiement_creance, ErreurFinance

        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response({"detail": "Lieu boutique requis."}, status=status.HTTP_400_BAD_REQUEST)

        # Scoping : la créance doit appartenir à cette boutique
        try:
            journal = JournalCreance.objects.get(pk=pk, lieu=lieu)
        except JournalCreance.DoesNotExist:
            return Response({"detail": "Créance introuvable."}, status=status.HTTP_404_NOT_FOUND)

        from api.idempotency import IdempotencyGuard
        guard = IdempotencyGuard(request, "paiement_creance_boutique")
        early = guard.check()
        if early is not None:
            return early

        ser = PaiementCreanceCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            enregistrer_paiement_creance(
                journal=journal,
                montant=d["montant"],
                date=d["date"],
                created_by=request.user,
                mode_paiement=d.get("mode_paiement", "especes"),
                reference=d.get("reference", ""),
                notes=d.get("notes", ""),
            )
        except ErreurFinance as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        audit_log(
            user=request.user,
            action="paiement_creance_boutique",
            object_type="JournalCreance",
            object_id=journal.pk,
            extra={"montant": str(d["montant"]), "lieu": lieu.nom},
            request=request,
        )
        journal.refresh_from_db()
        resp_data = JournalCreanceSerializer(journal).data
        guard.success(resp_data)
        return Response(resp_data)


# ─── Transferts depuis boutique ───────────────────────────────────────────────

class DestinationsBoutiqueTransfertView(APIView):
    """
    GET /api/boutique/transferts/destinations/
    Liste les destinations disponibles pour un transfert depuis la boutique :
      - Autres boutiques de la même entreprise
      - Usines de la même entreprise
      - MPSL de la même entreprise
    La boutique source est exclue. Isolation cross-tenant garantie.
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get(self, request):
        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Boutique introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = Lieu.objects.filter(
            entreprise_id=lieu.entreprise_id,
            type_lieu__in=(Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE, Lieu.TYPE_MPSL),
        ).exclude(pk=lieu.pk).order_by("type_lieu", "nom")

        return Response([
            {
                "id": d.pk,
                "nom": d.nom,
                "type_lieu": d.type_lieu,
                "type_label": {
                    Lieu.TYPE_MAGASIN: "boutique",
                    Lieu.TYPE_USINE: "usine",
                    Lieu.TYPE_MPSL: "MPSL",
                }.get(d.type_lieu, d.type_lieu),
            }
            for d in qs
        ])


class TransfertBoutiqueView(APIView):
    """
    GET  /api/boutique/transferts/  — historique des transferts sortants de la boutique.
    POST /api/boutique/transferts/  — créer un transfert depuis la boutique.

    Body POST :
      {
        "to_lieu": <int>,
        "lignes": [
          {"produit_id": <int>, "quantite": "<decimal>", "unite": "sacs"|"kg"|"tonnes"},
          ...
        ]
      }

    Règles de sécurité :
      - from_boutique forcé à request.user.lieu (boutique) ou ?lieu= (admin).
      - to_lieu doit appartenir à la même entreprise.
      - Isolation cross-tenant vérifiée dans le service.
      - Idempotency-Key obligatoire.
    """
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]

    def get(self, request):
        from inventaire.models import Transfert

        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Boutique introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transferts = (
            Transfert.objects.filter(from_lieu=lieu)
            .select_related("from_lieu", "to_lieu")
            .prefetch_related("mouvements__produit")
            .order_by("-date")[:50]
        )
        return Response([
            {
                "id": t.pk,
                "date": t.date.isoformat(),
                "from_lieu": t.from_lieu.nom,
                "to_lieu": t.to_lieu.nom,
                "to_lieu_type": {
                    Lieu.TYPE_MAGASIN: "boutique",
                    Lieu.TYPE_USINE: "usine",
                    Lieu.TYPE_MPSL: "MPSL",
                }.get(t.to_lieu.type_lieu, t.to_lieu.type_lieu),
                "mouvements": [
                    {
                        "produit": m.produit.nom,
                        "quantite": str(m.quantite),
                        "unite": m.produit.unite or "kg",
                    }
                    for m in t.mouvements.all()
                ],
            }
            for t in transferts
        ])

    def post(self, request):
        from api.idempotency import IdempotencyGuard
        from decimal import InvalidOperation
        from inventaire.services import transfert_depuis_boutique

        guard = IdempotencyGuard(request, "transfert_boutique")
        early = guard.check()
        if early is not None:
            return early

        lieu = get_lieu_boutique(request)
        if not lieu:
            return Response(
                {"detail": "Boutique introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        to_lieu_id = request.data.get("to_lieu")
        lignes_raw = request.data.get("lignes", [])

        if not to_lieu_id:
            return Response(
                {"detail": "to_lieu est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not lignes_raw or not isinstance(lignes_raw, list):
            return Response(
                {"detail": "lignes est obligatoire et doit être une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Résoudre destination — anti-IDOR : scope par entreprise
        try:
            to_lieu = Lieu.objects.get(
                pk=to_lieu_id,
                entreprise_id=request.user.entreprise_id,
                type_lieu__in=(Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE, Lieu.TYPE_MPSL),
            )
        except Lieu.DoesNotExist:
            return Response(
                {"detail": "Destination introuvable ou hors entreprise."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Construire les lignes service
        lignes = []
        for i, l in enumerate(lignes_raw):
            produit_id = l.get("produit_id")
            quantite_raw = l.get("quantite")
            unite = (l.get("unite") or "kg").strip()

            if not produit_id or not quantite_raw:
                return Response(
                    {"detail": f"Ligne {i + 1} : produit_id et quantite sont obligatoires."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                quantite = Decimal(str(quantite_raw))
                if quantite <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                return Response(
                    {"detail": f"Ligne {i + 1} : quantite invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Anti-IDOR : le produit doit appartenir à l'entreprise
            try:
                produit = Produit.objects.get(
                    pk=produit_id,
                    entreprise_id=request.user.entreprise_id,
                )
            except Produit.DoesNotExist:
                return Response(
                    {"detail": f"Ligne {i + 1} : produit introuvable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lignes.append((produit, quantite, unite))

        try:
            transfert = transfert_depuis_boutique(
                from_boutique=lieu,
                to_lieu=to_lieu,
                lignes=lignes,
                updated_by=request.user,
                log_request=request,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        audit_log(
            user=request.user,
            action="transfert_depuis_boutique",
            object_type="Transfert",
            object_id=transfert.pk,
            extra={
                "from_lieu": lieu.nom,
                "to_lieu": to_lieu.nom,
                "nb_lignes": len(lignes),
            },
            request=request,
        )

        resp_data = {
            "id": transfert.pk,
            "date": transfert.date.isoformat(),
            "from_lieu": lieu.nom,
            "to_lieu": to_lieu.nom,
            "lignes": len(lignes),
        }
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)
