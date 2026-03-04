"""
Vues KONIS : impression ticket 58mm.
"""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import CustomUser
from core.models import Lieu
from ventes.models import Facture, Ticket


def _can_access_lieu_scoped_document(user, lieu_id: int) -> bool:
    if user.role == CustomUser.ROLE_ADMIN:
        return True
    if user.role == CustomUser.ROLE_COMPTABLE:
        if not user.entreprise_id:
            return False
        return Lieu.objects.filter(pk=lieu_id, entreprise_id=user.entreprise_id).exists()
    return bool(user.lieu_id and user.lieu_id == lieu_id)


def _get_query_param(request, key: str, default: str = "") -> str:
    if hasattr(request, "query_params"):
        return request.query_params.get(key, default)
    return request.GET.get(key, default)


def _facture_pdf_response(request, facture_id: int):
    facture = get_object_or_404(
        Facture.objects.prefetch_related("lignes__produit").select_related("lieu", "lieu__entreprise", "created_by"),
        pk=facture_id,
    )
    if not _can_access_lieu_scoped_document(request.user, facture.lieu_id):
        return Response({"detail": "Facture introuvable."}, status=404)

    try:
        from ventes.pdf import build_facture_pdf
    except Exception:
        return Response(
            {"detail": "Moteur PDF indisponible. Installez les dependances serveur (reportlab)."},
            status=503,
        )

    pdf = build_facture_pdf(facture)
    filename = f"facture-{facture.numero}.pdf"
    content_disposition = "attachment" if _get_query_param(request, "download") == "1" else "inline"

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'{content_disposition}; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ticket_print(request, ticket_id):
    """Page d'impression ticket 58mm. GET /ventes/ticket/<id>/print/"""
    ticket = get_object_or_404(
        Ticket.objects.prefetch_related("lignes__produit").select_related("lieu"),
        pk=ticket_id,
    )
    if not _can_access_lieu_scoped_document(request.user, ticket.lieu_id):
        return Response({"detail": "Ticket introuvable."}, status=404)
    total = sum(l.quantite * l.prix_unitaire for l in ticket.lignes.all())
    django_request = request._request if hasattr(request, "_request") else request
    return render(
        django_request,
        "ticket_print.html",
        {"ticket": ticket, "total": total},
        content_type="text/html; charset=utf-8",
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def facture_pdf(request, facture_id):
    """Facture PDF officielle A4. GET /ventes/facture/<id>/pdf/"""
    return _facture_pdf_response(request, facture_id)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def facture_print(request, facture_id):
    """Alias historique de print: renvoie le PDF officiel."""
    return _facture_pdf_response(request, facture_id)
