"""
Utilitaires partagés entre les views KONIS.
Centralise les helpers de résolution de lieu et de filtrage par date.
"""
from datetime import datetime

from rest_framework.exceptions import ValidationError

from core.models import CustomUser, Lieu


def _parse_date(value: str, param_name: str) -> str:
    """Valide et retourne une date YYYY-MM-DD ; lève ValidationError si invalide."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise ValidationError({param_name: f"Format de date invalide : '{value}'. Attendu : YYYY-MM-DD."})


def get_lieu_boutique(request) -> Lieu | None:
    """
    Résout le lieu (magasin) pour la requête courante.
    - Rôle boutique : retourne request.user.lieu directement.
    - Rôle admin    : cherche ?lieu= (query param) ou body["lieu"].
    Retourne None si aucun lieu trouvable.
    """
    if request.user.role in (CustomUser.ROLE_ADMIN, CustomUser.ROLE_SUPREME_ADMIN):
        lieu_id = request.query_params.get("lieu") or request.data.get("lieu")
        if not lieu_id:
            return None
        qs = Lieu.objects.filter(type_lieu=Lieu.TYPE_MAGASIN, pk=lieu_id)
        if request.user.entreprise_id:
            qs = qs.filter(entreprise_id=request.user.entreprise_id)
        return qs.first()
    return request.user.lieu


def get_lieu_usine(request) -> Lieu | None:
    """
    Résout le lieu (usine) pour la requête courante.
    - Rôle usine  : retourne request.user.lieu directement.
    - Rôle admin  : cherche ?lieu= ou body["lieu_usine"]/body["lieu"].
    Retourne None si aucun lieu trouvable.
    """
    if request.user.role in (CustomUser.ROLE_ADMIN, CustomUser.ROLE_SUPREME_ADMIN):
        lieu_id = (
            request.query_params.get("lieu")
            or request.data.get("lieu_usine")
            or request.data.get("lieu")
        )
        if lieu_id:
            qs = Lieu.objects.filter(pk=lieu_id, type_lieu=Lieu.TYPE_USINE)
            if request.user.entreprise_id:
                qs = qs.filter(entreprise_id=request.user.entreprise_id)
            return qs.first()
        return None

    if (
        request.user.role == CustomUser.ROLE_USINE
        and request.user.lieu
        and request.user.lieu.type_lieu == Lieu.TYPE_USINE
    ):
        return request.user.lieu
    return None


def get_lieu_mpsl(request) -> Lieu | None:
    """
    Résout le dépôt MPSL pour la requête courante.
    - Rôle admin    : utilise ?lieu= (query param) ou body["lieu"], sinon premier dépôt MPSL de l'entreprise.
    - Rôle mpsl     : utilise request.user.lieu s'il est de type mpsl, sinon premier dépôt MPSL de l'entreprise.
    L'utilisateur MPSL n'est PAS obligatoirement lié à un lieu — il opère sur tout dépôt MPSL de son entreprise.
    """
    ent = getattr(request.user, "entreprise_id", None)
    if request.user.role in (CustomUser.ROLE_ADMIN, CustomUser.ROLE_SUPREME_ADMIN):
        lieu_id = request.query_params.get("lieu") or request.data.get("lieu")
        if lieu_id:
            qs = Lieu.objects.filter(pk=lieu_id, type_lieu=Lieu.TYPE_MPSL)
            if ent:
                qs = qs.filter(entreprise_id=ent)
            return qs.first()
        return Lieu.objects.filter(type_lieu=Lieu.TYPE_MPSL, entreprise_id=ent).first() if ent else None
    if request.user.role == CustomUser.ROLE_MPSL:
        if request.user.lieu_id and request.user.lieu and request.user.lieu.type_lieu == Lieu.TYPE_MPSL:
            return request.user.lieu
        return Lieu.objects.filter(type_lieu=Lieu.TYPE_MPSL, entreprise_id=ent).first() if ent else None
    return None


def filter_by_lieu(queryset, request, field: str = "lieu"):
    """
    Filtre un queryset par ?lieu=<id> si le paramètre est présent.
    field : nom du champ FK lieu dans le modèle (default: 'lieu').
    """
    lieu_id = request.query_params.get("lieu")
    if lieu_id:
        queryset = queryset.filter(**{field: lieu_id})
    return queryset


def filter_by_date(queryset, request, field: str = "date"):
    """
    Filtre un queryset par ?date_debut=YYYY-MM-DD et/ou ?date_fin=YYYY-MM-DD.
    field : nom du champ date dans le modèle (default: 'date').
    """
    debut = request.query_params.get("date_debut") or request.query_params.get("start_date")
    fin = request.query_params.get("date_fin") or request.query_params.get("end_date")
    if debut:
        queryset = queryset.filter(**{f"{field}__date__gte": _parse_date(debut, "date_debut")})
    if fin:
        queryset = queryset.filter(**{f"{field}__date__lte": _parse_date(fin, "date_fin")})
    return queryset
