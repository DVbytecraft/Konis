"""
Serializers Finance KONIS — séparé de serializers.py pour la lisibilité.
"""
from decimal import Decimal

from rest_framework import serializers

from finance.models import (
    CaisseSupremeTransaction,
    ClientFinance,
    Creancier,
    DepenseProjet,
    DepotProjet,
    Emprunt,
    JournalCreance,
    JournalPayable,
    LigneCreance,
    PaiementCreance,
    PaiementPayable,
    Projet,
    RemboursementEmprunt,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

class MontantRestantMixin:
    """Ajoute le champ calculé montant_restant à un serializer."""
    def get_montant_restant(self, obj) -> str:
        return str(obj.montant_restant)


# ═══════════════════════════════════════════════════════════════════════════════
# CRÉANCIERS
# ═══════════════════════════════════════════════════════════════════════════════

class CreancierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Creancier
        fields = ("id", "nom", "type_creancier", "contact", "notes", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CreancierCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Creancier
        fields = ("nom", "type_creancier", "contact", "notes")


# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAUX PAYABLES
# ═══════════════════════════════════════════════════════════════════════════════

class PaiementPayableSerializer(serializers.ModelSerializer):
    mode_paiement_display = serializers.CharField(source="get_mode_paiement_display", read_only=True)

    class Meta:
        model = PaiementPayable
        fields = (
            "id", "montant", "date", "mode_paiement", "mode_paiement_display",
            "reference", "notes", "created_at",
        )
        read_only_fields = ("id", "created_at")


class JournalPayableSerializer(MontantRestantMixin, serializers.ModelSerializer):
    creancier_nom    = serializers.CharField(source="creancier.nom", read_only=True)
    montant_restant  = serializers.SerializerMethodField()
    statut_display   = serializers.CharField(source="get_statut_display", read_only=True)
    paiements        = PaiementPayableSerializer(many=True, read_only=True)

    class Meta:
        model = JournalPayable
        fields = (
            "id", "creancier", "creancier_nom", "reference", "description",
            "montant_initial", "montant_paye", "montant_restant",
            "statut", "statut_display", "date_echeance", "notes",
            "created_at", "locked_at", "paiements",
        )
        read_only_fields = ("id", "montant_paye", "statut", "created_at", "locked_at")


class JournalPayableCreateSerializer(serializers.Serializer):
    creancier_id  = serializers.IntegerField()
    description   = serializers.CharField()
    montant_initial = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    reference     = serializers.CharField(required=False, allow_blank=True, default="")
    date_echeance = serializers.DateField(required=False, allow_null=True, default=None)
    notes         = serializers.CharField(required=False, allow_blank=True, default="")


class PaiementPayableCreateSerializer(serializers.Serializer):
    montant       = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date          = serializers.DateField()
    mode_paiement = serializers.ChoiceField(
        choices=["especes", "cheque", "virement", "mobile", "autre"],
        default="especes",
    )
    reference     = serializers.CharField(required=False, allow_blank=True, default="")
    notes         = serializers.CharField(required=False, allow_blank=True, default="")


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTS FINANCE
# ═══════════════════════════════════════════════════════════════════════════════

class ClientFinanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientFinance
        fields = ("id", "nom", "contact", "notes", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ClientFinanceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientFinance
        fields = ("nom", "contact", "notes")


# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAUX CRÉANCES
# ═══════════════════════════════════════════════════════════════════════════════

class LigneCreanceSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True, default=None)
    total       = serializers.SerializerMethodField()

    def get_total(self, obj) -> str:
        return str(obj.total)

    class Meta:
        model = LigneCreance
        fields = ("id", "produit", "produit_nom", "description", "quantite", "prix_unitaire", "total")
        read_only_fields = ("id",)


class PaiementCreanceSerializer(serializers.ModelSerializer):
    mode_paiement_display = serializers.CharField(source="get_mode_paiement_display", read_only=True)

    class Meta:
        model = PaiementCreance
        fields = (
            "id", "montant", "date", "mode_paiement", "mode_paiement_display",
            "reference", "notes", "created_at",
        )
        read_only_fields = ("id", "created_at")


class JournalCreanceSerializer(MontantRestantMixin, serializers.ModelSerializer):
    client_nom      = serializers.CharField(source="client.nom", read_only=True)
    montant_restant = serializers.SerializerMethodField()
    statut_display  = serializers.CharField(source="get_statut_display", read_only=True)
    lignes          = LigneCreanceSerializer(many=True, read_only=True)
    paiements       = PaiementCreanceSerializer(many=True, read_only=True)

    class Meta:
        model = JournalCreance
        fields = (
            "id", "client", "client_nom", "reference", "description",
            "montant_initial", "montant_paye", "montant_restant",
            "statut", "statut_display", "date_echeance", "notes",
            "created_at", "locked_at", "lignes", "paiements",
        )
        read_only_fields = ("id", "montant_paye", "statut", "created_at", "locked_at")


class LigneCreanceInputSerializer(serializers.Serializer):
    description   = serializers.CharField()
    quantite      = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), default=Decimal("1"))
    prix_unitaire = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    produit_id    = serializers.IntegerField(required=False, allow_null=True, default=None)


class JournalCreanceCreateSerializer(serializers.Serializer):
    client_id       = serializers.IntegerField()
    description     = serializers.CharField()
    montant_initial = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    lignes          = LigneCreanceInputSerializer(many=True, required=False, default=list)
    reference       = serializers.CharField(required=False, allow_blank=True, default="")
    date_echeance   = serializers.DateField(required=False, allow_null=True, default=None)
    notes           = serializers.CharField(required=False, allow_blank=True, default="")


class PaiementCreanceCreateSerializer(serializers.Serializer):
    montant       = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date          = serializers.DateField()
    mode_paiement = serializers.ChoiceField(
        choices=["especes", "cheque", "virement", "mobile", "autre"],
        default="especes",
    )
    reference     = serializers.CharField(required=False, allow_blank=True, default="")
    notes         = serializers.CharField(required=False, allow_blank=True, default="")


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRUNTS
# ═══════════════════════════════════════════════════════════════════════════════

class RemboursementEmpruntSerializer(serializers.ModelSerializer):
    class Meta:
        model = RemboursementEmprunt
        fields = ("id", "montant", "date", "reference", "notes", "created_at")
        read_only_fields = ("id", "created_at")


class EmpruntSerializer(serializers.ModelSerializer):
    montant_restant = serializers.SerializerMethodField()
    statut_display  = serializers.CharField(source="get_statut_display", read_only=True)
    remboursements  = RemboursementEmpruntSerializer(many=True, read_only=True)

    def get_montant_restant(self, obj) -> str:
        return str(obj.montant_restant)

    class Meta:
        model = Emprunt
        fields = (
            "id", "nom", "banque",
            "montant_initial", "montant_rembourse", "montant_restant",
            "taux_interet", "date_debut", "date_echeance",
            "statut", "statut_display", "notes",
            "created_at", "locked_at", "remboursements",
        )
        read_only_fields = ("id", "montant_rembourse", "statut", "created_at", "locked_at")


class EmpruntCreateSerializer(serializers.Serializer):
    nom             = serializers.CharField()
    banque          = serializers.CharField()
    montant_initial = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date_debut      = serializers.DateField()
    taux_interet    = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True, default=None)
    date_echeance   = serializers.DateField(required=False, allow_null=True, default=None)
    notes           = serializers.CharField(required=False, allow_blank=True, default="")


class RemboursementCreateSerializer(serializers.Serializer):
    montant   = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date      = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    notes     = serializers.CharField(required=False, allow_blank=True, default="")


# ═══════════════════════════════════════════════════════════════════════════════
# CAISSE SUPRÊME
# ═══════════════════════════════════════════════════════════════════════════════

class CaisseTransactionSerializer(serializers.ModelSerializer):
    type_display    = serializers.CharField(source="get_type_transaction_display", read_only=True)
    created_by_nom  = serializers.CharField(source="created_by.get_full_name", read_only=True)

    class Meta:
        model = CaisseSupremeTransaction
        fields = (
            "id", "type_transaction", "type_display", "montant",
            "description", "reference", "date",
            "created_by_nom", "created_at",
        )
        read_only_fields = ("id", "created_at")


class CaisseTransactionCreateSerializer(serializers.Serializer):
    type_transaction = serializers.ChoiceField(choices=["depot", "retrait"])
    montant          = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    description      = serializers.CharField()
    date             = serializers.DateField()
    reference        = serializers.CharField(required=False, allow_blank=True, default="")


# ═══════════════════════════════════════════════════════════════════════════════
# PROJETS
# ═══════════════════════════════════════════════════════════════════════════════

class DepenseProjetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepenseProjet
        fields = ("id", "montant", "description", "date", "created_at")
        read_only_fields = ("id", "created_at")


class DepotProjetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepotProjet
        fields = ("id", "montant", "description", "date", "created_at")
        read_only_fields = ("id", "created_at")


class ProjetSerializer(serializers.ModelSerializer):
    statut_display  = serializers.CharField(source="get_statut_display", read_only=True)
    budget_restant  = serializers.SerializerMethodField()
    total_depenses  = serializers.SerializerMethodField()
    total_depots    = serializers.SerializerMethodField()
    depenses        = DepenseProjetSerializer(many=True, read_only=True)
    depots          = DepotProjetSerializer(many=True, read_only=True)

    def get_budget_restant(self, obj) -> str:
        from finance.services import get_budget_restant_projet
        return str(get_budget_restant_projet(obj))

    def get_total_depenses(self, obj) -> str:
        from django.db.models import Sum
        total = obj.depenses.aggregate(t=Sum("montant"))["t"]
        return str(total or "0")

    def get_total_depots(self, obj) -> str:
        from django.db.models import Sum
        total = obj.depots.aggregate(t=Sum("montant"))["t"]
        return str(total or "0")

    class Meta:
        model = Projet
        fields = (
            "id", "nom", "description",
            "budget_initial", "total_depots", "total_depenses", "budget_restant",
            "statut", "statut_display", "date_debut", "date_fin",
            "created_at", "updated_at", "depenses", "depots",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ProjetCreateSerializer(serializers.Serializer):
    nom            = serializers.CharField()
    description    = serializers.CharField(required=False, allow_blank=True, default="")
    budget_initial = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    date_debut     = serializers.DateField()
    date_fin       = serializers.DateField(required=False, allow_null=True, default=None)


class DepenseProjetCreateSerializer(serializers.Serializer):
    montant     = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField()
    date        = serializers.DateField()


class DepotProjetCreateSerializer(serializers.Serializer):
    montant     = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField()
    date        = serializers.DateField()


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD — Résumé financier global
# ═══════════════════════════════════════════════════════════════════════════════

class ResumeFinancierSerializer(serializers.Serializer):
    total_creances_restantes = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_payables_restants  = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_emprunts_restants  = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    solde_caisse             = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    projets_en_cours         = serializers.IntegerField(read_only=True)
    projets_en_depassement   = serializers.IntegerField(read_only=True)
