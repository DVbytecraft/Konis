"""
API Factures : creation/listing/detail pour admin/comptable/usine/boutique.
"""
from decimal import Decimal
from django.utils import timezone

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import FactureCreateSerializer, FactureSerializer
from core.models import CustomUser, Lieu
from produits.models import Produit
from ventes.models import Facture, LigneFacture

ALLOWED_ROLES = {
    CustomUser.ROLE_ADMIN,
    CustomUser.ROLE_COMPTABLE,
    CustomUser.ROLE_USINE,
    CustomUser.ROLE_BOUTIQUE,
}


def _is_factory_like(user: CustomUser) -> bool:
    return user.role == CustomUser.ROLE_USINE or user.is_factory()


def _get_lieu_for_creation(user: CustomUser, data) -> Lieu | None:
    """
    Boutique/Usine: lieu force = user.lieu.
    Admin/Comptable: lieu requis dans le payload.
    """
    if user.role == CustomUser.ROLE_BOUTIQUE or _is_factory_like(user):
        return user.lieu
    lieu_value = data.get("lieu")
    if not lieu_value:
        return None
    if isinstance(lieu_value, Lieu):
        lieu = lieu_value
    else:
        lieu = Lieu.objects.filter(pk=lieu_value).first()
    if not lieu:
        return None
    if user.role == CustomUser.ROLE_COMPTABLE and user.entreprise_id and lieu.entreprise_id != user.entreprise_id:
        return None
    return lieu


def _next_facture_number(lieu: Lieu) -> str:
    prefix = (lieu.code or lieu.nom or f"L{lieu.pk}")[:12].upper().replace(" ", "")
    date_part = timezone.now().strftime("%Y%m%d")
    last = (
        Facture.objects.filter(lieu=lieu, numero__startswith=f"INV-{prefix}-{date_part}-")
        .order_by("-id")
        .first()
    )
    seq = 1
    if last and last.numero:
        try:
            seq = int(last.numero.split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"INV-{prefix}-{date_part}-{seq:06d}"


class FactureListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self, request):
        if request.user.role not in ALLOWED_ROLES and not request.user.is_factory():
            return Facture.objects.none()
        qs = Facture.objects.select_related("lieu", "created_by").prefetch_related("lignes__produit").order_by("-date")
        if request.user.role in (CustomUser.ROLE_ADMIN, CustomUser.ROLE_COMPTABLE):
            if request.user.role == CustomUser.ROLE_COMPTABLE and request.user.entreprise_id:
                qs = qs.filter(lieu__entreprise_id=request.user.entreprise_id)
            lieu_id = request.query_params.get("lieu")
            if lieu_id:
                qs = qs.filter(lieu_id=lieu_id)
            return qs
        if not request.user.lieu_id:
            return Facture.objects.none()
        return qs.filter(lieu_id=request.user.lieu_id)

    def get(self, request):
        data = FactureSerializer(self.get_queryset(request), many=True).data
        return Response(data)

    def post(self, request):
        if request.user.role not in ALLOWED_ROLES and not request.user.is_factory():
            return Response({"detail": "Role non autorise."}, status=status.HTTP_403_FORBIDDEN)
        ser = FactureCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        lieu = _get_lieu_for_creation(request.user, ser.validated_data)
        if not lieu:
            return Response(
                {"detail": "Lieu invalide ou non autorise pour cette creation de facture."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lines_data = ser.validated_data["lignes"]
        with transaction.atomic():
            facture = Facture.objects.create(
                lieu=lieu,
                numero=_next_facture_number(lieu),
                source_role=CustomUser.ROLE_USINE if _is_factory_like(request.user) else request.user.role,
                created_by=request.user,
                client_nom=ser.validated_data.get("client_nom", ""),
                client_contact=ser.validated_data.get("client_contact", ""),
                notes=ser.validated_data.get("notes", ""),
                total=Decimal("0"),
            )
            total = Decimal("0")
            for line in lines_data:
                produit = None
                produit_raw = line.get("produit")
                if produit_raw:
                    produit_id = produit_raw.pk if hasattr(produit_raw, "pk") else int(produit_raw)
                    produit = Produit.objects.filter(
                        pk=produit_id, entreprise=request.user.entreprise
                    ).first()
                quantite = Decimal(str(line["quantite"]))
                prix_unitaire = Decimal(str(line["prix_unitaire"]))
                LigneFacture.objects.create(
                    facture=facture,
                    produit=produit,
                    description=str(line.get("description", "")).strip() or (produit.nom if produit else "Ligne"),
                    quantite=quantite,
                    prix_unitaire=prix_unitaire,
                )
                total += quantite * prix_unitaire
            facture.total = total
            facture.save(update_fields=["total"])

        return Response(FactureSerializer(facture).data, status=status.HTTP_201_CREATED)


class FactureDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk: int):
        qs = Facture.objects.select_related("lieu", "created_by").prefetch_related("lignes__produit")
        facture = qs.filter(pk=pk).first()
        if not facture:
            return None
        if request.user.role == CustomUser.ROLE_ADMIN:
            return facture
        if request.user.role == CustomUser.ROLE_COMPTABLE:
            if request.user.entreprise_id and facture.lieu.entreprise_id != request.user.entreprise_id:
                return None
            return facture
        if request.user.lieu_id and facture.lieu_id == request.user.lieu_id:
            return facture
        return None

    def get(self, request, pk: int):
        if request.user.role not in ALLOWED_ROLES and not request.user.is_factory():
            return Response({"detail": "Role non autorise."}, status=status.HTTP_403_FORBIDDEN)
        facture = self.get_object(request, pk)
        if not facture:
            return Response({"detail": "Facture introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(FactureSerializer(facture).data)
