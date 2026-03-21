from decimal import Decimal

from rest_framework import serializers

from core.models import Lieu
from inventaire.models import AchatUsine
from produits.models import Produit
from usine.models import LotProduction, TransfertCession, TransfertInterUsine


class LotProductionSerializer(serializers.ModelSerializer):
    lieu_usine_nom = serializers.CharField(source="lieu_usine.nom", read_only=True)
    produit_fini_nom = serializers.CharField(source="produit_fini.nom", read_only=True)
    produit_fini_code = serializers.CharField(source="produit_fini.code", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    stock_restant = serializers.SerializerMethodField()

    class Meta:
        model = LotProduction
        fields = (
            "id",
            "nom_lot",
            "lieu_usine",
            "lieu_usine_nom",
            "produit_fini",
            "produit_fini_nom",
            "produit_fini_code",
            "quantite_sacs",
            "poids",
            "unite_poids",
            "created_by",
            "created_by_username",
            "stock_restant",
            "created_at",
        )

    def get_stock_restant(self, obj):
        from inventaire.models import Stock
        s = Stock.objects.filter(produit=obj.produit_fini, lieu=obj.lieu_usine).first()
        return str(s.quantite) if s else "0"


class LotProductionCreateSerializer(serializers.Serializer):
    nom_lot = serializers.CharField(max_length=100)
    lieu_usine = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE))
    produit_fini = serializers.PrimaryKeyRelatedField(queryset=Produit.objects.all())
    quantite_sacs = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    poids = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))
    unite_poids = serializers.ChoiceField(choices=["kg", "tonnes"], default="kg", required=False)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        entreprise = getattr(getattr(request, "user", None), "entreprise", None)
        # Fail-safe : .none() si pas d'entreprise — évite IDOR cross-tenant
        fields["produit_fini"].queryset = (
            Produit.objects.filter(entreprise=entreprise, category=Produit.CATEGORY_FINISHED)
            if entreprise
            else Produit.objects.none()
        )
        return fields

    def validate(self, attrs):
        poids = attrs.get("poids", Decimal("0"))
        quantite_sacs = attrs.get("quantite_sacs", Decimal("0"))
        unite_poids = attrs.get("unite_poids", "kg")
        if poids > 0 and quantite_sacs > 0:
            poids_en_kg = poids * 1000 if unite_poids == "tonnes" else poids
            poids_par_sac_kg = poids_en_kg / quantite_sacs
            if poids_par_sac_kg > 1000:
                raise serializers.ValidationError({
                    "poids": (
                        f"Poids incohérent : {poids} {unite_poids} pour {quantite_sacs} sacs "
                        f"= {round(poids_par_sac_kg, 1)} kg/sac (max 1 000 kg/sac). "
                        "Vérifiez l'unité et le poids saisis."
                    )
                })
        return attrs


class TransfertCessionSerializer(serializers.ModelSerializer):
    lot_nom = serializers.CharField(source="lot.nom_lot", read_only=True)
    boutique_nom = serializers.CharField(source="boutique.nom", read_only=True)
    produit_nom = serializers.CharField(source="lot.produit_fini.nom", read_only=True)
    montant_cession = serializers.SerializerMethodField()

    class Meta:
        model = TransfertCession
        fields = (
            "id",
            "lot",
            "lot_nom",
            "produit_nom",
            "boutique",
            "boutique_nom",
            "quantite_sacs",
            "poids_total",
            "prix_par_sac",
            "montant_cession",
            "transfert",
            "created_at",
        )

    def get_montant_cession(self, obj):
        return str(obj.quantite_sacs * obj.prix_par_sac)


class TransfertCessionCreateSerializer(serializers.Serializer):
    lot = serializers.PrimaryKeyRelatedField(queryset=LotProduction.objects.all())
    boutique = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_MAGASIN))
    quantite_sacs = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    poids_total = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))
    prix_par_sac = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))

    def validate(self, attrs):
        poids_total = attrs.get("poids_total", Decimal("0"))
        quantite_sacs = attrs.get("quantite_sacs", Decimal("0"))
        if poids_total > 0 and quantite_sacs > 0:
            poids_par_sac_kg = poids_total / quantite_sacs
            if poids_par_sac_kg > 1000:
                raise serializers.ValidationError({
                    "poids_total": (
                        f"Poids incohérent : {poids_total} kg pour {quantite_sacs} sacs "
                        f"= {round(poids_par_sac_kg, 1)} kg/sac (max 1 000 kg/sac). "
                        "Vérifiez le poids total saisi."
                    )
                })
        return attrs


class AchatUsineSerializer(serializers.ModelSerializer):
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)

    class Meta:
        model = AchatUsine
        fields = (
            "id",
            "lieu",
            "lieu_nom",
            "produit_nom",
            "quantite",
            "unite",
            "prix_unitaire",
            "prix_total",
            "notes",
            "created_by",
            "date",
        )


class AchatUsineCreateSerializer(serializers.Serializer):
    lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE))
    produit_nom = serializers.CharField(max_length=255)
    quantite = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unite = serializers.ChoiceField(choices=["sacs", "kg", "tonnes"], default="sacs")
    prix_unitaire = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_produit_nom(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Le nom du produit est obligatoire.")
        return value.strip()


class TransfertInterUsineSerializer(serializers.ModelSerializer):
    lot_nom = serializers.CharField(source="lot.nom_lot", read_only=True)
    produit_nom = serializers.CharField(source="lot.produit_fini.nom", read_only=True)
    usine_source_nom = serializers.CharField(source="lot.lieu_usine.nom", read_only=True)
    usine_source = serializers.IntegerField(source="lot.lieu_usine.id", read_only=True)
    usine_destination_nom = serializers.CharField(source="usine_destination.nom", read_only=True)
    montant_transfert = serializers.SerializerMethodField()

    class Meta:
        model = TransfertInterUsine
        fields = (
            "id",
            "lot",
            "lot_nom",
            "produit_nom",
            "usine_source",
            "usine_source_nom",
            "usine_destination",
            "usine_destination_nom",
            "quantite_sacs",
            "poids_total",
            "prix_par_sac",
            "montant_transfert",
            "notes",
            "created_at",
        )

    def get_montant_transfert(self, obj):
        return str(obj.quantite_sacs * obj.prix_par_sac)


class TransfertInterUsineCreateSerializer(serializers.Serializer):
    lot = serializers.PrimaryKeyRelatedField(queryset=LotProduction.objects.all())
    usine_destination = serializers.PrimaryKeyRelatedField(
        queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE)
    )
    quantite_sacs = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    poids_total = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))
    prix_par_sac = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        poids_total = attrs.get("poids_total", Decimal("0"))
        quantite_sacs = attrs.get("quantite_sacs", Decimal("0"))
        if poids_total > 0 and quantite_sacs > 0:
            poids_par_sac_kg = poids_total / quantite_sacs
            if poids_par_sac_kg > 1000:
                raise serializers.ValidationError({
                    "poids_total": (
                        f"Poids incohérent : {poids_total} kg pour {quantite_sacs} sacs "
                        f"= {round(poids_par_sac_kg, 1)} kg/sac (max 1 000 kg/sac). "
                        "Vérifiez le poids total saisi."
                    )
                })
        return attrs


class TransfertDirectUsineCreateSerializer(serializers.Serializer):
    """Transfert direct depuis usine vers usine ou magasin (sans LotProduction, sans prix)."""
    from_lieu = serializers.PrimaryKeyRelatedField(
        queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE)
    )
    to_lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.all())
    lignes = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user and request.user.entreprise_id:
            ent_id = request.user.entreprise_id
            fields["from_lieu"].queryset = Lieu.objects.filter(
                type_lieu=Lieu.TYPE_USINE,
                entreprise_id=ent_id,
            )
            fields["to_lieu"].queryset = Lieu.objects.filter(
                type_lieu__in=[Lieu.TYPE_USINE, Lieu.TYPE_MAGASIN],
                entreprise_id=ent_id,
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
