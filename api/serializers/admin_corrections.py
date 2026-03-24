"""
Serializers pour les corrections d'urgence admin (caisse, stock, tickets).
Validation centralisée + cross-tenant checks.
"""
from decimal import Decimal
from rest_framework import serializers

from core.models import Lieu
from inventaire.models import Stock
from produits.models import Produit
from ventes.models import Ticket


class AdminCorrectionCaisseSerializer(serializers.Serializer):
    """Validation pour correction de caisse."""

    lieu_id = serializers.IntegerField(
        required=True,
        help_text="ID de la boutique à corriger"
    )
    montant = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=True,
        help_text="Montant à ajouter ou retrancher (doit être positif)"
    )
    operation = serializers.ChoiceField(
        choices=["ajouter", "retrancher"],
        default="ajouter",
        help_text="Opération : 'ajouter' ou 'retrancher'"
    )
    motif = serializers.CharField(
        max_length=500,
        required=True,
        help_text="Motif de la correction (obligatoire)"
    )

    def validate_montant(self, value):
        """Montant doit être positif."""
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être positif.")
        return value

    def validate_motif(self, value):
        """Motif ne peut pas être vide."""
        if not value or not value.strip():
            raise serializers.ValidationError("Le motif est obligatoire.")
        return value.strip()

    def validate_lieu_id(self, value):
        """Vérifier que le lieu existe et est une boutique."""
        try:
            lieu = Lieu.objects.get(pk=value, type_lieu=Lieu.TYPE_MAGASIN)
        except Lieu.DoesNotExist:
            raise serializers.ValidationError("Boutique introuvable ou pas un magasin.")

        # Cross-tenant check via context
        request = self.context.get("request")
        if request and request.user and request.user.entreprise_id:
            if lieu.entreprise_id != request.user.entreprise_id:
                raise serializers.ValidationError("Boutique non autorisée pour votre entreprise.")

        return value


class AdminCorrectionStockSerializer(serializers.Serializer):
    """Validation pour correction de stock."""

    lieu_id = serializers.IntegerField(
        required=True,
        help_text="ID du lieu"
    )
    produit_id = serializers.IntegerField(
        required=True,
        help_text="ID du produit"
    )
    quantite = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Quantité (non requise pour 'supprimer')"
    )
    operation = serializers.ChoiceField(
        choices=["ajouter", "retrancher", "supprimer"],
        default="ajouter",
        help_text="Opération : 'ajouter', 'retrancher', ou 'supprimer'"
    )
    motif = serializers.CharField(
        max_length=500,
        required=True,
        help_text="Motif de la correction (obligatoire)"
    )

    def validate(self, data):
        """Valider l'ensemble des données."""
        operation = data.get("operation")
        quantite = data.get("quantite")

        # quantite requise sauf pour "supprimer"
        if operation != "supprimer" and not quantite:
            raise serializers.ValidationError(
                {"quantite": "Quantité requise pour cette opération."}
            )

        return data

    def validate_quantite(self, value):
        """Quantité doit être positive si présente."""
        if value is not None and value < 0:
            raise serializers.ValidationError("La quantité ne peut pas être négative.")
        return value

    def validate_motif(self, value):
        """Motif ne peut pas être vide."""
        if not value or not value.strip():
            raise serializers.ValidationError("Le motif est obligatoire.")
        return value.strip()

    def validate_lieu_id(self, value):
        """Vérifier que le lieu existe."""
        try:
            lieu = Lieu.objects.get(pk=value)
        except Lieu.DoesNotExist:
            raise serializers.ValidationError("Lieu introuvable.")

        # Cross-tenant check
        request = self.context.get("request")
        if request and request.user and request.user.entreprise_id:
            if lieu.entreprise_id != request.user.entreprise_id:
                raise serializers.ValidationError("Lieu non autorisé pour votre entreprise.")

        return value

    def validate_produit_id(self, value):
        """Vérifier que le produit existe."""
        try:
            Produit.objects.get(pk=value)
        except Produit.DoesNotExist:
            raise serializers.ValidationError("Produit introuvable.")

        return value


class AdminSupprimerTicketSerializer(serializers.Serializer):
    """Validation pour suppression de ticket."""

    motif = serializers.CharField(
        max_length=500,
        required=True,
        help_text="Motif de suppression du ticket (obligatoire)"
    )

    def validate_motif(self, value):
        """Motif ne peut pas être vide."""
        if not value or not value.strip():
            raise serializers.ValidationError("Le motif est obligatoire.")
        return value.strip()
