"""
API Admin Corrections - Corrections d'urgence pour les erreurs de vente/stock/caisse.
Réservé exclusivement aux admins/supreme_admin.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import permission_classes
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
from inventaire.models import Stock
from ventes.models import Ticket


@permission_classes([IsAdminRole])
class AdminCorrectionCaisseView(APIView):
    """
    POST /api/admin/corrections/caisse/
    Corrige le montant de la caisse d'une boutique.

    Body: {"lieu_id": int, "montant": decimal, "operation": "ajouter|retrancher", "motif": str}
    """

    def post(self, request):
        # Valider les données avec le serializer
        serializer = AdminCorrectionCaisseSerializer(
            data=request.data,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Récupérer les données validées
        lieu_id = serializer.validated_data["lieu_id"]
        montant = serializer.validated_data["montant"]
        operation = serializer.validated_data["operation"]
        motif = serializer.validated_data["motif"]

        # Récupérer le lieu
        lieu = Lieu.objects.get(pk=lieu_id, type_lieu=Lieu.TYPE_MAGASIN)

        # Créer un mouvement de caisse fictif pour corriger
        from finance.models import CaisseSupremeTransaction
        from finance.services import get_solde_caisse

        entreprise = lieu.entreprise
        old_solde = get_solde_caisse(entreprise)

        if operation == "retrancher":
            # Pour retrancher, on enregistre un "retrait" fictif de la caisse centrale
            tx = CaisseSupremeTransaction.objects.create(
                entreprise=entreprise,
                type_transaction="retrait",
                montant=montant,
                description=f"CORRECTION CAISSE: {motif} (retrait pour équilibrer boutique {lieu.nom})",
                date=timezone.now().date(),
                created_by=request.user,
            )
            action = "caisse_correction_retrait"
            new_solde = old_solde - montant
        else:
            # Pour ajouter, on enregistre un "dépôt" fictif
            tx = CaisseSupremeTransaction.objects.create(
                entreprise=entreprise,
                type_transaction="depot",
                montant=montant,
                description=f"CORRECTION CAISSE: {motif} (ajout pour équilibrer boutique {lieu.nom})",
                date=timezone.now().date(),
                created_by=request.user,
            )
            action = "caisse_correction_depot"
            new_solde = old_solde + montant

        audit_log(
            user=request.user,
            action=action,
            object_type="CaisseSupremeTransaction",
            object_id=tx.pk,
            extra={
                "lieu_id": lieu.pk,
                "lieu_nom": lieu.nom,
                "montant": str(montant),
                "operation": operation,
                "motif": motif,
                "solde_avant": str(old_solde),
                "solde_apres": str(new_solde),
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
            "solde_avant": str(old_solde),
            "solde_apres": str(new_solde),
        })


@permission_classes([IsAdminRole])
class AdminCorrectionStockView(APIView):
    """
    POST /api/admin/corrections/stock/
    Corrige le stock d'un produit dans une boutique.

    Body: {"lieu_id": int, "produit_id": int, "quantite": decimal, "operation": "ajouter|retrancher|supprimer", "motif": str}
    """

    def post(self, request):
        # Valider les données avec le serializer
        serializer = AdminCorrectionStockSerializer(
            data=request.data,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Récupérer les données validées
        lieu_id = serializer.validated_data["lieu_id"]
        produit_id = serializer.validated_data["produit_id"]
        quantite = serializer.validated_data.get("quantite", Decimal("0"))
        operation = serializer.validated_data["operation"]
        motif = serializer.validated_data["motif"]

        # Récupérer lieu et produit (serializer a déjà vérifié)
        lieu = Lieu.objects.get(pk=lieu_id)
        from produits.models import Produit
        produit = Produit.objects.get(pk=produit_id)

        old_qty = Decimal("0")
        new_qty = Decimal("0")

        with transaction.atomic():
            stock, created = Stock.objects.get_or_create(
                lieu=lieu,
                produit=produit,
                defaults={"quantite": Decimal("0"), "quantite_kg": Decimal("0")}
            )
            old_qty = stock.quantite

            if operation == "ajouter":
                stock.quantite += quantite
                new_qty = stock.quantite
            elif operation == "retrancher":
                if quantite and quantite > stock.quantite:
                    return Response(
                        {"detail": f"Impossible de retrancher {quantite}: stock actuel = {stock.quantite}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                stock.quantite -= quantite if quantite else Decimal("0")
                new_qty = stock.quantite
            elif operation == "supprimer":
                new_qty = Decimal("0")
                stock.quantite = Decimal("0")

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


@permission_classes([IsAdminRole])
class AdminSupprimerTicketView(APIView):
    """
    POST /api/admin/corrections/ticket/{ticket_id}/
    Supprime un ticket en cas d'erreur de paiement.
    Retourne le montant au stock et ajuste la caisse.
    """

    def post(self, request, ticket_id):
        # Valider le motif avec le serializer
        serializer = AdminSupprimerTicketSerializer(
            data=request.data,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        motif = serializer.validated_data["motif"]

        try:
            ticket = Ticket.objects.select_related("lieu").prefetch_related("lignes__produit").get(pk=ticket_id)
        except Ticket.DoesNotExist:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # Vérifier l'entreprise
        if request.user.entreprise_id and ticket.lieu.entreprise_id != request.user.entreprise_id:
            return Response({"detail": "Ticket non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            # 1. Retourner les produits au stock
            from inventaire.models import MouvementStock
            for ligne in ticket.lignes.all():
                if ligne.produit:
                    try:
                        stock, _ = Stock.objects.get_or_create(
                            lieu=ticket.lieu,
                            produit=ligne.produit,
                            defaults={"quantite": Decimal("0"), "quantite_kg": Decimal("0")}
                        )
                        stock.quantite += ligne.quantite
                        stock.save()
                        MouvementStock.objects.create(
                            stock=stock,
                            type_mouvement="entree",
                            quantite=ligne.quantite,
                            notes=f"Annulation ticket #{ticket.numero}",
                            created_by=request.user,
                        )
                    except Exception:
                        pass  # On continue même si erreur stock

            # 2. Créer une correction de caisse (retirer le cash perçu)
            from finance.models import CaisseSupremeTransaction
            from finance.services import get_solde_caisse

            entreprise = ticket.lieu.entreprise
            old_solde = get_solde_caisse(entreprise)

            if ticket.montant_cash > 0:
                CaisseSupremeTransaction.objects.create(
                    entreprise=entreprise,
                    type_transaction="retrait",
                    montant=ticket.montant_cash,
                    description=f"ANNULATION TICKET #{ticket.numero}: {motif}",
                    date=ticket.date,
                    created_by=request.user,
                )

            # 3. Enregistrer l'annulation (pas de modification du ticket lui-même)
            # Le ticket reste inchangé - c'est juste l'audit qui enregistre l'annulation

            new_solde = get_solde_caisse(entreprise)

        audit_log(
            user=request.user,
            action="ticket_annule",
            object_type="Ticket",
            object_id=ticket.pk,
            extra={
                "ticket_numero": ticket.numero,
                "lieu_id": ticket.lieu.pk,
                "lieu_nom": ticket.lieu.nom,
                "montant_total": str(ticket.montant_total),
                "montant_cash": str(ticket.montant_cash),
                "montant_credit": str(ticket.montant_credit),
                "motif": motif,
                "solde_avant": str(old_solde),
                "solde_apres": str(new_solde),
            },
            request=request,
        )

        return Response({
            "success": True,
            "ticket_id": ticket.pk,
            "ticket_numero": ticket.numero,
            "lieu_nom": ticket.lieu.nom,
            "montant_total": str(ticket.montant_total),
            "montant_cash": str(ticket.montant_cash),
            "montant_credit": str(ticket.montant_credit),
            "motif": motif,
            "solde_caisse_avant": str(old_solde),
            "solde_caisse_apres": str(new_solde),
        })