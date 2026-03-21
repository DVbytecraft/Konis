from decimal import Decimal

from rest_framework import serializers

from core.models import Lieu
from inventaire.models import AchatMPSL


class AchatMPSLSerializer(serializers.ModelSerializer):
    lieu_nom             = serializers.CharField(source="lieu.nom",              read_only=True)
    fournisseur_nom      = serializers.CharField(source="fournisseur.nom",       read_only=True, default=None)
    created_by_username  = serializers.CharField(source="created_by.username",   read_only=True)
    type_paiement_label  = serializers.SerializerMethodField()
    journal_payable_id   = serializers.IntegerField(source="journal_payable.id", read_only=True, default=None)

    def get_type_paiement_label(self, obj):
        return obj.get_type_paiement_display()

    class Meta:
        model = AchatMPSL
        fields = (
            "id",
            "lieu", "lieu_nom",
            "fournisseur", "fournisseur_nom",
            "produit_nom",
            "quantite", "unite",
            "prix_unitaire", "prix_total",
            "type_paiement", "type_paiement_label",
            "montant_paye_initial",
            "journal_payable_id",
            "notes",
            "created_by", "created_by_username",
            "date",
        )
        read_only_fields = ("prix_total", "created_by", "date", "journal_payable_id", "type_paiement_label")


class AchatMPSLCreateSerializer(serializers.Serializer):
    produit_nom   = serializers.CharField(max_length=255)
    quantite      = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unite         = serializers.ChoiceField(choices=AchatMPSL.UNITE_CHOICES, default=AchatMPSL.UNITE_SACS)
    prix_unitaire = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    notes         = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    poids_par_sac = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"),
        required=False, allow_null=True, default=None,
        help_text="Poids en kg d'un sac. Renseigner si unite='sacs' pour activer la conversion sacs→kg.",
    )
    # Fournisseur & paiement
    fournisseur_id       = serializers.IntegerField(required=False, allow_null=True, default=None,
                                help_text="ID du Créancier (fournisseur). Requis si type_paiement ≠ cash.")
    type_paiement        = serializers.ChoiceField(
        choices=AchatMPSL.TYPE_PAIEMENT_CHOICES, default=AchatMPSL.TYPE_CASH,
        help_text="'cash' | 'credit' | 'partiel'",
    )
    montant_paye_initial = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
        help_text="Acompte versé si type_paiement='partiel'.",
    )

    def validate(self, data):
        if data.get("type_paiement") in ("credit", "partiel") and not data.get("fournisseur_id"):
            raise serializers.ValidationError(
                {"fournisseur_id": "Le fournisseur est requis pour un achat à crédit ou partiel."}
            )
        if (data.get("unite") or "").lower() in ("sac", "sacs") and not data.get("poids_par_sac"):
            raise serializers.ValidationError({"poids_par_sac": "Poids par sac requis si l'unité est en sacs."})
        return data


class TransfertMPSLCreateSerializer(serializers.Serializer):
    """Transfert depuis MPSL vers usine ou magasin (mouvement pur, sans prix)."""
    to_lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.all())
    lignes = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user and request.user.entreprise_id:
            fields["to_lieu"].queryset = Lieu.objects.filter(
                type_lieu__in=[Lieu.TYPE_USINE, Lieu.TYPE_MAGASIN],
                entreprise_id=request.user.entreprise_id,
            )
        return fields

    def validate_lignes(self, value):
        from decimal import InvalidOperation
        errors = []
        for i, item in enumerate(value):
            produit_id = item.get("produit_id") or item.get("produit")
            quantite_raw = item.get("quantite")
            unite_raw = (item.get("unite") or "").strip().lower()
            if unite_raw and unite_raw not in ("sac", "sacs", "kg", "tonne", "tonnes"):
                errors.append(f"Ligne {i + 1} : unité invalide ('{unite_raw}').")
            if not produit_id:
                errors.append(f"Ligne {i + 1} : produit_id manquant.")
                continue
            try:
                quantite = Decimal(str(quantite_raw))
                if quantite <= 0:
                    errors.append(f"Ligne {i + 1} : quantité doit être > 0.")
            except (InvalidOperation, TypeError):
                errors.append(f"Ligne {i + 1} : quantité invalide.")
        if errors:
            raise serializers.ValidationError(errors)
        return value
