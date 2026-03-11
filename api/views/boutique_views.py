"""
API Boutique : stock (mon lieu), produits, ventes (créer / lister).
Filtre strict par lieu = request.user.lieu (rôle boutique).

Règles d'accès :
  - Produits : lecture seule pour boutique (création via usine uniquement)
  - Stock : lecture seule pour boutique (alimentation via cessions usine uniquement)
  - Ventes : création + lecture pour boutique et admin
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count

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
from ventes.services import vente_boutique, vente_mouture_seule


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
        prix_mouture_tonne = ser.validated_data.get("prix_mouture_tonne")
        prix_mouture_sac = ser.validated_data.get("prix_mouture_sac")

        try:
            ticket = vente_boutique(
                lieu,
                lignes,
                mouture=mouture,
                prix_mouture_kg=prix_mouture_kg,
                prix_mouture_tonne=prix_mouture_tonne,
                prix_mouture_sac=prix_mouture_sac,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
            },
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

        produit_nom = ser.validated_data.get("produit_nom", "")
        ticket, created = vente_mouture_seule(
            lieu=lieu,
            quantite=ser.validated_data["quantite"],
            unite=ser.validated_data["unite"],
            prix_unitaire=ser.validated_data["prix_unitaire"],
            produit_apporte=produit_nom,
            idempotency_key=idempotency_key,
        )

        if created:
            audit_log(
                user=request.user,
                action="mouture_seule_créée",
                object_type="ticket",
                object_id=ticket.pk,
                extra={"numero": ticket.numero, "montant_total": str(ticket.montant_total)},
            )
        else:
            audit_log(
                user=request.user,
                action="mouture_seule_rejouee",
                object_type="ticket",
                object_id=ticket.pk,
                extra={"numero": ticket.numero, "idempotency_key": idempotency_key},
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
        )
        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)
