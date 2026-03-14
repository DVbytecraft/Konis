"""
API Admin : supervision et administration entreprise.
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from audit.services import audit_log
from api.permissions import IsAdminRole
from api.serializers import (
    AchatUsineSerializer,
    CategorieDepenseSerializer,
    CategorieSerializer,
    DepenseSerializer,
    EntrepriseSerializer,
    FactoryCreateSerializer,
    FactorySerializer,
    FactoryUpdateSerializer,
    LieuSerializer,
    ProduitSerializer,
    StockSerializer,
    TicketSerializer,
    TransfertSerializer,
    UserSerializer,
)
from core.models import Entreprise, Lieu, CustomUser
from depenses.models import CategorieDepense, Depense
from inventaire.models import AchatUsine, Stock, Transfert
from produits.models import Categorie, Produit
from ventes.models import Ticket


def _filter_by_lieu(qs, request, lieu_field="lieu"):
    """Applique le filtre ?lieu=id sur le queryset."""
    lieu_id = request.query_params.get("lieu")
    if lieu_id:
        return qs.filter(**{f"{lieu_field}": lieu_id})
    return qs


def _ensure_user_entreprise(user: CustomUser) -> Entreprise:
    """
    Assure qu'un utilisateur admin est rattaché à une entreprise.
    Si aucune entreprise n'existe encore, en crée une par défaut.
    """
    if getattr(settings, "SINGLE_ENTREPRISE", False):
        entreprise = Entreprise.get_primary()
        if user.entreprise_id != entreprise.id:
            user.entreprise = entreprise
            user.save(update_fields=["entreprise"])
        return entreprise
    if user.entreprise_id:
        return user.entreprise
    entreprise = Entreprise.get_primary()
    user.entreprise = entreprise
    user.save(update_fields=["entreprise"])
    return entreprise


def _get_effective_entreprise_id(request) -> int | None:
    if getattr(settings, "SINGLE_ENTREPRISE", False):
        return Entreprise.get_primary().id
    if request.user and request.user.entreprise_id:
        return request.user.entreprise_id
    entreprise_id = request.query_params.get("entreprise")
    if entreprise_id and str(entreprise_id).isdigit():
        return int(entreprise_id)
    return None


def _bump_locations_cache_version() -> None:
    """Bump cache version to invalidate locations-by-type cache."""
    key = "locations_by_type_version"
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=None)


class EntrepriseViewSet(ModelViewSet):
    queryset = Entreprise.objects.all()
    serializer_class = EntrepriseSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = super().get_queryset().order_by("id")
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(pk=effective_id)
        return qs

    def create(self, request, *args, **kwargs):
        if getattr(settings, "SINGLE_ENTREPRISE", False):
            return Response(
                {"detail": "Creation d'entreprise desactivee en mode mono-entreprise."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if getattr(settings, "SINGLE_ENTREPRISE", False):
            return Response(
                {"detail": "Suppression d'entreprise desactivee en mode mono-entreprise."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class LieuViewSet(ModelViewSet):
    queryset = Lieu.objects.all().select_related("entreprise")
    serializer_class = LieuSerializer
    permission_classes = [IsAdminRole]

    def perform_create(self, serializer):
        entreprise = _ensure_user_entreprise(self.request.user)
        serializer.save(entreprise=entreprise)
        _bump_locations_cache_version()

    def perform_update(self, serializer):
        serializer.save()
        _bump_locations_cache_version()

    def perform_destroy(self, instance):
        instance.delete()
        _bump_locations_cache_version()

    def get_queryset(self):
        qs = super().get_queryset().order_by("id")
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(entreprise_id=effective_id)
        lieu_id = self.request.query_params.get("lieu")
        if lieu_id:
            qs = qs.filter(pk=lieu_id)
        type_lieu = self.request.query_params.get("type_lieu")
        if type_lieu:
            normalized = {
                "shop": Lieu.TYPE_MAGASIN,
                "magasin": Lieu.TYPE_MAGASIN,
                "factory": Lieu.TYPE_USINE,
                "usine": Lieu.TYPE_USINE,
            }.get(type_lieu.lower(), type_lieu.lower())
            qs = qs.filter(type_lieu=normalized)
        return qs


class FactoryViewSet(ModelViewSet):
    """Admin: création et gestion des usines + compte utilisateur usine associé."""

    permission_classes = [IsAdminRole]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE).select_related("entreprise", "compte_boutique")
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(entreprise_id=effective_id)
        active = self.request.query_params.get("active")
        if active in ("true", "false"):
            qs = qs.filter(is_active=(active == "true"))
        return qs.order_by("nom")

    def get_serializer_class(self):
        if self.action == "create":
            return FactoryCreateSerializer
        if self.action in ("partial_update", "update"):
            return FactoryUpdateSerializer
        return FactorySerializer

    def list(self, request, *args, **kwargs):
        data = FactorySerializer(self.get_queryset(), many=True).data
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        factory = self.get_object()
        return Response(FactorySerializer(factory).data)

    def create(self, request, *args, **kwargs):
        ser = FactoryCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        entreprise = ser.validated_data.get("entreprise")
        if getattr(settings, "SINGLE_ENTREPRISE", False) or entreprise is None:
            entreprise = _ensure_user_entreprise(request.user)

        email = ser.validated_data["user_email"].strip().lower()
        username_base = email.split("@")[0] if "@" in email else email
        username = username_base
        i = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{username_base}{i}"
            i += 1

        with transaction.atomic():
            factory = Lieu.objects.create(
                entreprise=entreprise,
                nom=ser.validated_data["factory_name"],
                adresse=ser.validated_data.get("factory_address", ""),
                type_lieu=Lieu.TYPE_USINE,
                is_active=True,
            )
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password=ser.validated_data["user_password"],
                first_name=ser.validated_data.get("user_first_name", ""),
                last_name=ser.validated_data.get("user_last_name", ""),
                role=CustomUser.ROLE_USINE,
                entreprise=entreprise,
                lieu=factory,
                is_active=True,
            )
            group, _ = Group.objects.get_or_create(name="Factory")
            user.groups.add(group)
        _bump_locations_cache_version()

        audit_log(
            user=request.user,
            action="factory_created",
            object_type="lieu",
            object_id=factory.pk,
            extra={"factory_id": factory.pk, "factory_user_id": user.pk},
        )
        return Response(FactorySerializer(factory).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        factory = self.get_object()
        try:
            user = factory.compte_boutique
        except CustomUser.DoesNotExist:
            user = None
        ser = FactoryUpdateSerializer(data=request.data, partial=True, context={"instance": factory, "user": user})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        with transaction.atomic():
            if "factory_name" in data:
                factory.nom = data["factory_name"]
            if "factory_address" in data:
                factory.adresse = data["factory_address"]
            if "is_active" in data:
                factory.is_active = data["is_active"]
            factory.save()

            if user:
                if "user_email" in data:
                    user.email = data["user_email"].strip().lower()
                if "user_first_name" in data:
                    user.first_name = data["user_first_name"]
                if "user_last_name" in data:
                    user.last_name = data["user_last_name"]
                if "is_active" in data:
                    user.is_active = data["is_active"]
                if "user_password" in data:
                    user.set_password(data["user_password"])
                user.save()
        _bump_locations_cache_version()

        audit_log(
            user=request.user,
            action="factory_updated",
            object_type="lieu",
            object_id=factory.pk,
            extra={"factory_id": factory.pk},
        )
        return Response(FactorySerializer(factory).data)

    def destroy(self, request, *args, **kwargs):
        factory = self.get_object()
        factory.is_active = False
        factory.save(update_fields=["is_active"])
        try:
            user = factory.compte_boutique
        except CustomUser.DoesNotExist:
            user = None
        if user:
            user.is_active = False
            user.save(update_fields=["is_active"])
        _bump_locations_cache_version()
        audit_log(
            user=request.user,
            action="factory_deactivated",
            object_type="lieu",
            object_id=factory.pk,
            extra={"factory_id": factory.pk},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LocationByTypeView(APIView):
    """GET /api/locations/by-type/?type=shop|factory."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        type_param = (request.query_params.get("type") or "").strip().lower()
        type_map = {
            "shop": Lieu.TYPE_MAGASIN,
            "magasin": Lieu.TYPE_MAGASIN,
            "boutique": Lieu.TYPE_MAGASIN,
            "factory": Lieu.TYPE_USINE,
            "usine": Lieu.TYPE_USINE,
        }
        if type_param and type_param not in type_map:
            return Response(
                {"detail": "type doit être 'shop' ou 'factory'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        include_inactive = (request.query_params.get("include_inactive") or "").strip().lower() in ("1", "true", "yes")
        effective_ent = _get_effective_entreprise_id(request)
        version = cache.get("locations_by_type_version") or 1
        cache_key = f"locations_by_type:v{version}:ent:{effective_ent or 'none'}:type:{type_param or 'all'}:inactive:{include_inactive}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        qs = Lieu.objects.all().select_related("entreprise")
        if request.user.role != CustomUser.ROLE_ADMIN and effective_ent is None:
            return Response([], status=status.HTTP_200_OK)
        if effective_ent:
            qs = qs.filter(entreprise_id=effective_ent)
        if not include_inactive:
            qs = qs.filter(is_active=True)
        if type_param:
            qs = qs.filter(type_lieu=type_map[type_param])

        # Retourner un format simplifie pour les selects
        data = []
        for l in qs:
            if l.type_lieu == Lieu.TYPE_MAGASIN:
                type_lieu = "shop"
                type_lieu_raw = "magasin"
            else:
                type_lieu = "factory"
                type_lieu_raw = "usine"
            data.append({
                "id": l.id,
                "nom": l.nom,
                "name": l.nom,
                "type_lieu": type_lieu,
                "type_lieu_raw": type_lieu_raw,
            })
        payload = {"count": len(data), "results": data}
        cache.set(cache_key, payload, timeout=60)
        return Response(payload)


class UserViewSet(ModelViewSet):
    queryset = CustomUser.objects.all().select_related("lieu", "entreprise")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = super().get_queryset().order_by("id")
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(entreprise_id=effective_id)
        lieu_id = self.request.query_params.get("lieu")
        if lieu_id:
            qs = qs.filter(lieu_id=lieu_id)
        return qs

    def perform_create(self, serializer):
        entreprise = _ensure_user_entreprise(self.request.user)
        serializer.save(entreprise=entreprise)

    def perform_update(self, serializer):
        old_role = serializer.instance.role
        user = serializer.save()
        extra = {"user_id": user.pk}
        if old_role != user.role:
            extra["role_before"] = old_role
            extra["role_after"] = user.role
        audit_log(
            user=self.request.user,
            action="user_updated",
            object_type="user",
            object_id=user.pk,
            extra=extra,
        )

    def perform_destroy(self, instance):
        audit_log(
            user=self.request.user,
            action="user_deleted",
            object_type="user",
            object_id=instance.pk,
            extra={"username": instance.username, "role": instance.role},
        )
        instance.delete()


class CategorieViewSet(ModelViewSet):
    queryset = Categorie.objects.all()
    serializer_class = CategorieSerializer
    permission_classes = [IsAdminRole]


class ProduitViewSet(ModelViewSet):
    """Admin supervision: lecture seule des produits (filtrés par entreprise de l'admin)."""
    serializer_class = ProduitSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id is None:
            return Produit.objects.none()
        return Produit.objects.filter(entreprise_id=effective_id).select_related("categorie")


class StockViewSet(ModelViewSet):
    queryset = Stock.objects.all().select_related("produit", "lieu")
    serializer_class = StockSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = super().get_queryset()
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(lieu__entreprise_id=effective_id)
        return _filter_by_lieu(qs, self.request)


class TransfertViewSet(ModelViewSet):
    queryset = Transfert.objects.all().select_related("from_lieu", "to_lieu").prefetch_related("mouvements__produit")
    serializer_class = TransfertSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(from_lieu__entreprise_id=effective_id)
        lieu_id = self.request.query_params.get("lieu")
        if lieu_id:
            qs = qs.filter(from_lieu_id=lieu_id) | qs.filter(to_lieu_id=lieu_id)
        return qs.distinct()


class AchatUsineViewSet(ModelViewSet):
    queryset = AchatUsine.objects.all().select_related("lieu", "created_by")
    serializer_class = AchatUsineSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(lieu__entreprise_id=effective_id)
        return _filter_by_lieu(qs, self.request)


class TicketAdminViewSet(ModelViewSet):
    """Admin : liste des tickets (lecture). Création via boutique ou admin avec lieu."""
    queryset = Ticket.objects.all().select_related("lieu").prefetch_related("lignes__produit").order_by("-date")
    serializer_class = TicketSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(lieu__entreprise_id=effective_id)
        return _filter_by_lieu(qs, self.request)


class CategorieDepenseViewSet(ModelViewSet):
    queryset = CategorieDepense.objects.all()
    serializer_class = CategorieDepenseSerializer
    permission_classes = [IsAdminRole]


class DepenseViewSet(ModelViewSet):
    queryset = Depense.objects.all().select_related("lieu", "categorie")
    serializer_class = DepenseSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = super().get_queryset()
        effective_id = _get_effective_entreprise_id(self.request)
        if effective_id:
            qs = qs.filter(lieu__entreprise_id=effective_id)
        return _filter_by_lieu(qs, self.request)

    def perform_create(self, serializer):
        depense = serializer.save()
        audit_log(
            user=self.request.user,
            action="depense_ajoutee",
            object_type="depense",
            object_id=depense.pk,
            extra={"lieu_id": depense.lieu_id, "montant": str(depense.montant)},
        )
