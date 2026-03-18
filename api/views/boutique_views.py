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
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from audit.services import audit_log
from api.permissions import IsAdminRole, IsBoutiqueRole
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
from ventes.services import normaliser_quantite_en_kg, vente_boutique, vente_mouture_seule


class StockBoutiqueViewSet(ModelViewSet):
    """
    GET  /api/boutique/stock/ : stock du lieu (boutique et admin).
    POST /api/boutique/stock/ : entrée manuelle réservée aux admins uniquement.
    Les boutiques reçoivent du stock exclusivement via les cessions usine.
    """
    serializer_class = StockSerializer
    permission_classes = [IsAuthenticated, IsBoutiqueRole | IsAdminRole]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        lieu = get_lieu_boutique(self.request)
        if not lieu:
            return Stock.objects.none()
        return Stock.objects.filter(lieu=lieu).select_related("produit", "lieu")

    def create(self, request, *args, **kwargs):
        """Réservé aux admins — les boutiques ne peuvent pas entrer du stock directement."""
        if request.user.role != CustomUser.ROLE_ADMIN:
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

        ser = BoutiqueStockReceiptSerializer(data=request.data)
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
            stock.save(update_fields=["quantite"])

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
            qs = qs.filter(date__date__gte=debut)
        if fin:
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
        lignes_data = ser.validated_data["lignes"]

        # Chargement des produits en 1 seule requête (évite N+1)
        produit_ids = [
            item["produit"] if isinstance(item["produit"], int) else item["produit"].pk
            for item in lignes_data
        ]
        produits_map = {
            p.pk: p
            for p in Produit.objects.filter(pk__in=produit_ids, entreprise=lieu.entreprise)
        }
        lignes = []
        for item in lignes_data:
            produit_id = item["produit"] if isinstance(item["produit"], int) else item["produit"].pk
            produit = produits_map.get(produit_id)
            if produit is None:
                return Response(
                    {"detail": f"Produit inconnu ou non autorisé : {produit_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quantite = Decimal(str(item["quantite"]))
            prix_unitaire = Decimal(str(item["prix_unitaire"]))
            lignes.append((produit, quantite, prix_unitaire))

        mouture = ser.validated_data.get("mouture", False)
        prix_mouture_kg = ser.validated_data.get("prix_mouture_kg")

        # ── Garde-fou prix mouture ──────────────────────────────────────────
        if mouture and prix_mouture_kg and lieu.prix_mouture_max and prix_mouture_kg > lieu.prix_mouture_max:
            return Response(
                {
                    "detail": (
                        f"Prix mouture {prix_mouture_kg} FCFA/kg dépasse le plafond autorisé "
                        f"({lieu.prix_mouture_max} FCFA/kg). Contactez l'administrateur."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Grain apporté par le client — normaliser en kg
        quantite_apportee_client_kg = Decimal("0")
        if mouture:
            qty_apportee = ser.validated_data.get("quantite_apportee_mouture") or Decimal("0")
            if qty_apportee > 0:
                unite_apportee = ser.validated_data.get("unite_apportee_mouture", "kg")
                produit_ref_apportee = None
                produit_id_apportee = ser.validated_data.get("produit_id_apportee")
                if produit_id_apportee:
                    try:
                        produit_ref_apportee = Produit.objects.get(
                            pk=produit_id_apportee, entreprise=lieu.entreprise
                        )
                    except Produit.DoesNotExist:
                        return Response(
                            {"detail": f"Produit apportée {produit_id_apportee} introuvable."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                try:
                    quantite_apportee_client_kg = normaliser_quantite_en_kg(
                        qty_apportee, unite_apportee, produit_ref_apportee
                    )
                except ErreurStock as e:
                    return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = vente_boutique(
                lieu,
                lignes,
                mouture=mouture,
                prix_mouture_kg=prix_mouture_kg,
                quantite_apportee_client_kg=quantite_apportee_client_kg,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
                "montant_total": str(ticket.montant_total),
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
        idempotency_key = request.headers.get("Idempotency-Key", "").strip() or None
        if idempotency_key and len(idempotency_key) > 128:
            return Response(
                {"detail": "Header Idempotency-Key trop long (max 128)."},
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
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable

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

        story = [
            Paragraph("KONIS — Service Mouture", title_style),
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
        fname = f"mouture_{lieu.nom.replace(' ', '_')}_{debut}_{fin}.pdf"
        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        return response
