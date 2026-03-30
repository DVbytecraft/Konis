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
    # Acompte réellement enregistré sur le JournalPayable lié.
    # Pour les achats uniques  : == montant_paye_initial (identiques).
    # Pour les achats batch    : montant_paye_initial vaut 0 sur chaque ligne
    #   (fix S5 — évite la duplication × N), mais le vrai acompte versé est ici.
    # Le frontend doit lire ce champ en priorité sur montant_paye_initial.
    journal_montant_paye = serializers.DecimalField(
        source="journal_payable.montant_paye",
        read_only=True, default=None,
        max_digits=14, decimal_places=2,
    )

    def get_type_paiement_label(self, obj):
        return obj.get_type_paiement_display()

    class Meta:
        model = AchatMPSL
        fields = (
            "id",
            "lieu", "lieu_nom",
            "fournisseur", "fournisseur_nom",
            "produit_nom",
            "quantite", "unite", "poids_par_sac",
            "prix_unitaire", "prix_total",
            "type_paiement", "type_paiement_label",
            "montant_paye_initial",
            "journal_payable_id",
            "journal_montant_paye",
            "notes",
            "created_by", "created_by_username",
            "date",
        )
        read_only_fields = (
            "prix_total", "created_by", "date",
            "journal_payable_id", "journal_montant_paye", "type_paiement_label",
        )


def _validate_entier(value, nom_champ):
    """Lève ValidationError si value a une partie décimale non nulle."""
    if value is not None and value != value.to_integral_value():
        raise serializers.ValidationError(
            f"{nom_champ} doit être un nombre entier (reçu : {value})."
        )
    return value


class AchatMPSLCreateSerializer(serializers.Serializer):
    produit_nom   = serializers.CharField(max_length=255)
    quantite      = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))
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

    def validate_quantite(self, value):
        return _validate_entier(value, "La quantité")

    def validate_prix_unitaire(self, value):
        return _validate_entier(value, "Le prix unitaire")

    def validate_montant_paye_initial(self, value):
        return _validate_entier(value, "L'acompte")

    def validate(self, data):
        if data.get("type_paiement") in ("credit", "partiel") and not data.get("fournisseur_id"):
            raise serializers.ValidationError(
                {"fournisseur_id": "Le fournisseur est requis pour un achat à crédit ou partiel."}
            )
        # poids_par_sac est facultatif : le produit rejoint le catalogue sans poids.
        # Les conversions sac→kg seront indisponibles jusqu'à ce qu'il soit renseigné.
        return data


# ── Sérialiseur pour une ligne de produit dans un achat groupé ────────────────

class _LigneProduitBatchSerializer(serializers.Serializer):
    produit_nom   = serializers.CharField(max_length=255)
    quantite      = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))
    unite         = serializers.ChoiceField(choices=AchatMPSL.UNITE_CHOICES, default=AchatMPSL.UNITE_SACS)
    poids_par_sac = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"),
        required=False, allow_null=True, default=None,
    )
    prix_unitaire = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    notes         = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate_quantite(self, value):
        return _validate_entier(value, "La quantité")

    def validate_prix_unitaire(self, value):
        return _validate_entier(value, "Le prix unitaire")

    def validate(self, data):
        # poids_par_sac est facultatif ; conversions sac→kg indisponibles sans lui.
        return data


class AchatMPSLBatchSerializer(serializers.Serializer):
    """
    Crée plusieurs AchatMPSL en une seule transaction atomique.
    Un seul JournalPayable est créé pour la totalité si type_paiement ≠ cash.
    """
    type_paiement  = serializers.ChoiceField(
        choices=AchatMPSL.TYPE_PAIEMENT_CHOICES, default=AchatMPSL.TYPE_CASH,
    )
    fournisseur_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    # Nom du nouveau fournisseur si fournisseur_id est absent et type_paiement ≠ cash
    fournisseur_nom = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    acompte        = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
        help_text="Acompte global versé (uniquement si type_paiement='partiel').",
    )
    produits = serializers.ListField(
        child=_LigneProduitBatchSerializer(),
        min_length=1,
        max_length=50,
    )

    def validate_acompte(self, value):
        return _validate_entier(value, "L'acompte")

    def validate(self, data):
        tp = data.get("type_paiement", "cash")
        if tp in ("credit", "partiel"):
            if not data.get("fournisseur_id") and not (data.get("fournisseur_nom") or "").strip():
                raise serializers.ValidationError(
                    {"fournisseur_id": "Fournisseur requis (id existant ou nom pour création) pour achat à crédit/partiel."}
                )
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
