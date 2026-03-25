"""
API Admin Corrections - Corrections d'urgence pour les erreurs de vente/stock/caisse.
Réservé exclusivement aux admins/supreme_admin.
"""
from decimal import Decimal
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsAdminRole
from api.serializers.admin_corrections import (
    AdminCorrectionCaisseSerializer,
    AdminCorrectionStockSerializer,
    AdminSupprimerTicketSerializer,
)
from audit.services import audit_log
from core.models import Lieu
from finance.models import CorrectionCaisseAdmin
from finance.services import get_caisse_physique_boutique
from inventaire.models import Stock
from ventes.models import Ticket


class AdminCorrectionHistoriqueView(APIView):
    """
    GET /api/admin/corrections/historique/?lieu_id=X
    Retourne la caisse physique actuelle + l'historique des corrections admin.
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        lieu_id = request.query_params.get("lieu_id")
        if not lieu_id:
            return Response({"detail": "Paramètre lieu_id requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lieu = Lieu.objects.get(pk=lieu_id, type_lieu=Lieu.TYPE_MAGASIN)
        except Lieu.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.entreprise_id and lieu.entreprise_id != request.user.entreprise_id:
            return Response({"detail": "Boutique non autorisée."}, status=status.HTTP_403_FORBIDDEN)

        caisse_physique = get_caisse_physique_boutique(lieu)

        corrections = (
            CorrectionCaisseAdmin.objects
            .filter(lieu=lieu)
            .select_related("created_by")
            .order_by("-created_at")[:50]
        )

        return Response({
            "caisse_physique": str(caisse_physique),
            "corrections": [
                {
                    "id": c.pk,
                    "montant": str(c.montant),
                    "motif": c.motif,
                    "created_by": c.created_by.username if c.created_by else "—",
                    "created_at": c.created_at.strftime("%d/%m/%Y %H:%M"),
                }
                for c in corrections
            ],
        })


class AdminCorrectionCaisseView(APIView):
    """
    POST /api/admin/corrections/caisse/
    Corrige le solde de la caisse physique d'une boutique.
    Crée une CorrectionCaisseAdmin intégrée dans get_caisse_physique_boutique().

    Body: {"lieu_id": int, "montant": decimal, "operation": "ajouter|retrancher", "motif": str}
    """
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = AdminCorrectionCaisseSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        lieu_id  = serializer.validated_data["lieu_id"]
        montant  = serializer.validated_data["montant"]
        operation = serializer.validated_data["operation"]
        motif    = serializer.validated_data["motif"]

        try:
            lieu = Lieu.objects.get(pk=lieu_id, type_lieu=Lieu.TYPE_MAGASIN)
        except Lieu.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # Vérifier que le lieu appartient à l'entreprise de l'admin
        if request.user.entreprise_id and lieu.entreprise_id != request.user.entreprise_id:
            return Response({"detail": "Boutique non autorisée."}, status=status.HTTP_403_FORBIDDEN)

        old_caisse = get_caisse_physique_boutique(lieu)

        # montant signé : positif = ajout, négatif = retrait
        montant_signe = montant if operation == "ajouter" else -montant

        correction = CorrectionCaisseAdmin.objects.create(
            lieu=lieu,
            montant=montant_signe,
            motif=motif,
            created_by=request.user,
        )

        new_caisse = get_caisse_physique_boutique(lieu)

        audit_log(
            user=request.user,
            action=f"caisse_correction_{operation}",
            object_type="CorrectionCaisseAdmin",
            object_id=correction.pk,
            extra={
                "lieu_id": lieu.pk,
                "lieu_nom": lieu.nom,
                "montant": str(montant),
                "operation": operation,
                "motif": motif,
                "caisse_avant": str(old_caisse),
                "caisse_apres": str(new_caisse),
            },
            request=request,
        )

        return Response({
            "success": True,
            "lieu_id": lieu.pk,
            "lieu_nom": lieu.nom,
            "operation": operation,
            "montant": str(montant),
            "motif": motif,
            "caisse_avant": str(old_caisse),
            "caisse_apres": str(new_caisse),
        })


class AdminCorrectionStockView(APIView):
    """
    POST /api/admin/corrections/stock/
    Corrige le stock d'un produit dans une boutique.

    Body: {"lieu_id": int, "produit_id": int, "quantite": decimal, "operation": "ajouter|retrancher|supprimer", "motif": str}
    """
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = AdminCorrectionStockSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        lieu_id   = serializer.validated_data["lieu_id"]
        produit_id = serializer.validated_data["produit_id"]
        quantite  = serializer.validated_data.get("quantite", Decimal("0"))
        operation = serializer.validated_data["operation"]
        motif     = serializer.validated_data["motif"]

        try:
            lieu = Lieu.objects.get(pk=lieu_id)
        except Lieu.DoesNotExist:
            return Response({"detail": "Lieu introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.entreprise_id and lieu.entreprise_id != request.user.entreprise_id:
            return Response({"detail": "Lieu non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        from produits.models import Produit
        try:
            produit = Produit.objects.get(pk=produit_id)
        except Produit.DoesNotExist:
            return Response({"detail": "Produit introuvable."}, status=status.HTTP_404_NOT_FOUND)

        old_qty = Decimal("0")
        new_qty = Decimal("0")

        with transaction.atomic():
            stock, _ = Stock.objects.select_for_update().get_or_create(
                lieu=lieu,
                produit=produit,
                defaults={"quantite": Decimal("0"), "quantite_kg": Decimal("0")},
            )
            old_qty = stock.quantite

            if operation == "ajouter":
                stock.quantite += quantite
            elif operation == "retrancher":
                if quantite > stock.quantite:
                    return Response(
                        {"detail": f"Impossible de retrancher {quantite} : stock actuel = {stock.quantite}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                stock.quantite -= quantite
            elif operation == "supprimer":
                stock.quantite = Decimal("0")

            new_qty = stock.quantite
            stock.save()

        audit_log(
            user=request.user,
            action=f"stock_correction_{operation}",
            object_type="Stock",
            object_id=stock.pk,
            extra={
                "lieu_id": lieu.pk,
                "lieu_nom": lieu.nom,
                "produit_id": produit.pk,
                "produit_nom": produit.nom,
                "operation": operation,
                "quantite": str(quantite) if operation != "supprimer" else "supprimé",
                "quantite_avant": str(old_qty),
                "quantite_apres": str(new_qty),
                "motif": motif,
            },
            request=request,
        )

        return Response({
            "success": True,
            "lieu_id": lieu.pk,
            "lieu_nom": lieu.nom,
            "produit_id": produit.pk,
            "produit_nom": produit.nom,
            "operation": operation,
            "quantite_avant": str(old_qty),
            "quantite_apres": str(new_qty),
            "motif": motif,
        })


class AdminSupprimerTicketView(APIView):
    """
    POST /api/admin/corrections/ticket/{ticket_id}/
    Supprime définitivement un ticket erroné.
    - Restitue le stock de chaque ligne vendue.
    - Supprime TicketReprint, LigneVente, puis Ticket.
    - La caisse physique se corrige automatiquement (montant_cash du ticket n'est plus compté).
    """
    permission_classes = [IsAdminRole]

    def post(self, request, ticket_id):
        serializer = AdminSupprimerTicketSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        motif = serializer.validated_data["motif"]

        try:
            ticket = (
                Ticket.objects.select_related("lieu")
                .prefetch_related("lignes__produit", "reprints")
                .get(pk=ticket_id)
            )
        except Ticket.DoesNotExist:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.entreprise_id and ticket.lieu.entreprise_id != request.user.entreprise_id:
            return Response({"detail": "Ticket non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        # Si le ticket a une part crédit → une JournalCreance existe peut-être
        if ticket.montant_credit and ticket.montant_credit > 0:
            return Response(
                {
                    "detail": (
                        f"Ce ticket contient une part à crédit de {ticket.montant_credit} FCFA. "
                        "Soldez ou supprimez d'abord la créance associée dans le journal des créances."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Snapshot avant suppression pour l'audit
        snapshot = {
            "ticket_numero": ticket.numero,
            "lieu_id": ticket.lieu.pk,
            "lieu_nom": ticket.lieu.nom,
            "montant_total": str(ticket.montant_total),
            "montant_cash": str(ticket.montant_cash),
            "motif": motif,
            "lignes": [
                {
                    "produit_id": l.produit.pk if l.produit else None,
                    "produit_nom": l.produit.nom if l.produit else None,
                    "quantite": str(l.quantite),
                }
                for l in ticket.lignes.all()
            ],
        }

        with transaction.atomic():
            # 1. Restituer le stock pour chaque ligne
            for ligne in ticket.lignes.all():
                if ligne.produit:
                    stock, _ = Stock.objects.get_or_create(
                        lieu=ticket.lieu,
                        produit=ligne.produit,
                        defaults={"quantite": Decimal("0"), "quantite_kg": Decimal("0")},
                    )
                    stock = Stock.objects.select_for_update().get(pk=stock.pk)
                    stock.quantite += ligne.quantite
                    stock.save(update_fields=["quantite", "updated_at"])

            # 2. Supprimer les logs de réimpression (PROTECT)
            ticket.reprints.all().delete()

            # 3. Supprimer les lignes de vente (PROTECT)
            ticket.lignes.all().delete()

            # 4. Supprimer le ticket lui-même
            # La caisse physique se recalcule automatiquement : montant_cash n'est plus en base.
            ticket.delete()

        audit_log(
            user=request.user,
            action="ticket_supprime",
            object_type="Ticket",
            object_id=ticket_id,
            extra=snapshot,
            request=request,
        )

        return Response({
            "success": True,
            **snapshot,
        })
