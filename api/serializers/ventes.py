from decimal import Decimal

from rest_framework import serializers

from core.models import Lieu
from ventes.models import Facture, LigneFacture, LigneVente, Ticket


class LigneVenteSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = LigneVente
        fields = ("id", "produit", "produit_nom", "unite", "quantite", "prix_unitaire", "total")


class TicketSerializer(serializers.ModelSerializer):
    lignes = LigneVenteSerializer(many=True, read_only=True)
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)
    lignes_count = serializers.SerializerMethodField()
    mouture_source = serializers.SerializerMethodField()
    client_nom = serializers.SerializerMethodField()
    client_contact = serializers.SerializerMethodField()
    type_vente_label = serializers.SerializerMethodField()

    def get_lignes_count(self, obj):
        return len(obj.lignes.all())

    def get_mouture_source(self, obj):
        if not obj.mouture:
            return None
        return "mouture_seule" if self.get_lignes_count(obj) == 0 else "vente_avec_mouture"

    def get_client_nom(self, obj):
        return obj.client.nom if obj.client_id else None

    def get_client_contact(self, obj):
        return obj.client.contact if obj.client_id and obj.client else None

    def get_type_vente_label(self, obj):
        return obj.get_type_vente_display()

    class Meta:
        model = Ticket
        fields = (
            "id", "lieu", "lieu_nom", "date", "numero", "lignes",
            # Type de vente
            "type_vente", "type_vente_label",
            "montant_cash", "montant_credit",
            "client", "client_nom", "client_contact",
            # Mouture
            "produit_apporte", "mouture", "type_mouture",
            "prix_mouture_kg", "prix_mouture_tonne", "prix_mouture_sac",
            "quantite_apportee_client", "nombre_sacs", "poids_par_sac",
            "cout_mouture", "montant_total", "lignes_count", "mouture_source",
        )
        read_only_fields = ("type_vente_label", "client_nom", "client_contact", "lignes_count", "mouture_source")


class VenteBoutiqueCreateSerializer(serializers.Serializer):
    lignes = serializers.ListField(
        child=serializers.DictField(),
        help_text="[{produit: int, quantite: decimal, prix_unitaire: decimal, unite?: 'kg'|'sac'}, ...]",
    )
    # ── Type de vente ────────────────────────────────────────────────────────
    type_vente = serializers.ChoiceField(
        choices=Ticket.TYPE_VENTE_CHOICES,
        default=Ticket.TYPE_CASH,
        help_text="'cash' | 'credit' | 'partiel'",
    )
    montant_cash = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
        required=False, allow_null=True, default=None,
        help_text="Acompte versé si type_vente='partiel'. Ignoré si cash ou credit.",
    )
    client_id = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        help_text="ID ClientFinance — requis si type_vente = credit ou partiel.",
    )
    # ── Champs mouture — formule unifiée en kg ───────────────────────────────
    mouture = serializers.BooleanField(default=False)
    prix_mouture_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        required=False, allow_null=True, default=None,
        help_text="Prix mouture FCFA/kg. Toutes les unités sont normalisées en kg.",
    )
    # Grain supplémentaire apporté par le client (en plus des produits achetés)
    quantite_apportee_mouture = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
        help_text="Quantité grain apportée par le client (dans l'unité unite_apportee_mouture).",
    )
    unite_apportee_mouture = serializers.ChoiceField(
        choices=["kg", "tonne", "sac"],
        required=False, default="kg",
        help_text="Unité de la quantité apportée.",
    )
    produit_id_apportee = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        help_text="ID produit pour conversion sac→kg (poids_par_sac). Requis si unite_apportee_mouture='sac'.",
    )

    def validate_lignes(self, value):
        for item in value:
            for key in ("produit", "quantite", "prix_unitaire"):
                if key not in item:
                    raise serializers.ValidationError(f"Chaque ligne doit avoir {key}.")
            try:
                quantite = Decimal(str(item["quantite"]))
                prix = Decimal(str(item["prix_unitaire"]))
            except Exception:
                raise serializers.ValidationError("quantite et prix_unitaire doivent être des nombres valides.")
            if quantite <= 0:
                raise serializers.ValidationError("Quantité doit être > 0.")
            if prix < 0:
                raise serializers.ValidationError("Prix unitaire doit être >= 0.")
            if prix == 0:
                produit_info = item.get("produit", "?")
                raise serializers.ValidationError(
                    f"Prix unitaire à 0 FCFA non autorisé (produit {produit_info}). "
                    "Saisissez le prix réel ou annulez la ligne."
                )
        return value

    def validate(self, data):
        type_vente = data.get("type_vente", Ticket.TYPE_CASH)
        if type_vente in (Ticket.TYPE_CREDIT, Ticket.TYPE_PARTIEL):
            if not data.get("client_id"):
                raise serializers.ValidationError(
                    {"client_id": "Un client est requis pour une vente à crédit ou partielle."}
                )
        if type_vente == Ticket.TYPE_PARTIEL:
            if data.get("montant_cash") is None:
                raise serializers.ValidationError(
                    {"montant_cash": "L'acompte (montant_cash) est requis pour une vente partielle."}
                )
        if data.get("mouture"):
            if not data.get("prix_mouture_kg"):
                raise serializers.ValidationError(
                    "Mouture demandée : prix_mouture_kg (FCFA/kg) est requis. "
                    "Toutes les unités (sac, tonne) sont normalisées en kg avant calcul."
                )
            if (data.get("quantite_apportee_mouture") or Decimal("0")) > 0:
                if data.get("unite_apportee_mouture") == "sac" and not data.get("produit_id_apportee"):
                    raise serializers.ValidationError(
                        "unite_apportee_mouture='sac' : produit_id_apportee requis "
                        "pour la conversion kg (poids_par_sac)."
                    )
        return data


class MoutureSeuleSerializer(serializers.Serializer):
    """
    Sérialiseur pour le service mouture-seule (sans déduction de stock).

    Supporte 3 scénarios :
      1. Mouture seule     — quantite_apportee > 0, quantite_achetee = 0
      2. Mouture étendue   — quantite_apportee > 0, quantite_achetee > 0
      3. Achat seul moudre — quantite_apportee = 0, quantite_achetee > 0

    Formule : cout = (apportee_kg + achetee_kg) × prix_par_kg
    """
    quantite_apportee = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
        help_text="Quantité apportée par le client (dans l'unité 'unite').",
    )
    quantite_achetee = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0"),
        required=False, default=Decimal("0"),
        help_text="Quantité achetée/additionnelle à moudre (dans l'unité 'unite').",
    )
    unite = serializers.ChoiceField(
        choices=["kg", "tonne", "sac"],
        help_text="Unité de mesure commune aux deux quantités.",
    )
    prix_par_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        help_text="Prix mouture FCFA/kg. Toutes les unités sont normalisées en kg.",
    )
    produit_nom = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default="",
        help_text="Nom du grain apporté (ex: Maïs, Manioc…). Affiché sur le ticket.",
    )
    produit_id = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        help_text="ID produit pour conversion sac→kg (poids_par_sac). Requis si unite='sac'.",
    )
    # Traçabilité saisie par sacs (optionnel)
    nombre_sacs = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1,
        help_text="Nombre de sacs (renseigné si saisie en mode 'par sacs').",
    )
    poids_par_sac = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"),
        required=False, allow_null=True, default=None,
        help_text="Poids par sac en kg (renseigné si saisie en mode 'par sacs').",
    )

    def validate(self, data):
        total = data.get("quantite_apportee", Decimal("0")) + data.get("quantite_achetee", Decimal("0"))
        if total <= Decimal("0"):
            raise serializers.ValidationError(
                "La somme quantite_apportee + quantite_achetee doit être > 0."
            )
        if data.get("unite") == "sac" and not data.get("produit_id"):
            raise serializers.ValidationError(
                "unite='sac' : produit_id requis pour la conversion kg (poids_par_sac)."
            )
        return data


class LigneFactureSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = LigneFacture
        fields = ("id", "produit", "produit_nom", "description", "quantite", "prix_unitaire", "total")


class FactureSerializer(serializers.ModelSerializer):
    lignes = LigneFactureSerializer(many=True, read_only=True)
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Facture
        fields = (
            "id",
            "numero",
            "date",
            "source_role",
            "lieu",
            "lieu_nom",
            "created_by",
            "created_by_username",
            "client_nom",
            "client_contact",
            "notes",
            "total",
            "lignes",
        )


class FactureCreateSerializer(serializers.Serializer):
    lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.none(), required=False)
    client_nom = serializers.CharField(required=False, allow_blank=True, default="")
    client_contact = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lignes = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="[{produit: int?, description: str, quantite: decimal, prix_unitaire: decimal}]",
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        ent_id = getattr(getattr(request, "user", None), "entreprise_id", None)
        fields["lieu"].queryset = (
            Lieu.objects.filter(entreprise_id=ent_id) if ent_id else Lieu.objects.none()
        )
        return fields

    def validate_lignes(self, value):
        for item in value:
            if "description" not in item:
                raise serializers.ValidationError("Chaque ligne doit contenir description.")
            for key in ("quantite", "prix_unitaire"):
                if key not in item:
                    raise serializers.ValidationError(f"Chaque ligne doit contenir {key}.")
            if Decimal(str(item["quantite"])) <= 0:
                raise serializers.ValidationError("quantite doit etre > 0.")
            if Decimal(str(item["prix_unitaire"])) < 0:
                raise serializers.ValidationError("prix_unitaire doit etre >= 0.")
            if Decimal(str(item["prix_unitaire"])) == 0:
                raise serializers.ValidationError(
                    "prix_unitaire à 0 FCFA non autorisé. Saisissez le prix réel ou annulez la ligne."
                )
        return value


class TicketReprintCreateSerializer(serializers.Serializer):
    """Serializer pour enregistrer une réimpression de ticket."""
    motif = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
