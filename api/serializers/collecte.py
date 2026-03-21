from decimal import Decimal

from rest_framework import serializers

from finance.models import CollecteArgent


class CollecteArgentSerializer(serializers.ModelSerializer):
    lieu_nom         = serializers.CharField(source="lieu.nom",         read_only=True)
    collecteur_nom   = serializers.CharField(source="collecteur.username", read_only=True, default=None)
    created_by_nom   = serializers.CharField(source="created_by.username", read_only=True, default=None)
    depot_banque_id  = serializers.IntegerField(source="depot_banque.id",  read_only=True, default=None)

    class Meta:
        model  = CollecteArgent
        fields = (
            "id",
            "lieu", "lieu_nom",
            "collecteur", "collecteur_nom",
            "date_collecte",
            "montant_trouve", "montant_pris", "montant_laisse",
            "depot_banque_id",
            "notes",
            "created_by", "created_by_nom",
            "created_at",
        )
        read_only_fields = ("montant_laisse", "depot_banque_id", "created_by", "created_at")


class CollecteArgentCreateSerializer(serializers.Serializer):
    lieu_id          = serializers.IntegerField(help_text="ID de la boutique visitée.")
    date_collecte    = serializers.DateField()
    montant_trouve   = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    montant_pris     = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    notes            = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    deposer_en_banque = serializers.BooleanField(
        default=False,
        help_text="Si True, crée automatiquement un dépôt CaisseSupremeTransaction.",
    )

    def validate(self, data):
        if data["montant_pris"] > data["montant_trouve"]:
            raise serializers.ValidationError(
                {"montant_pris": "montant_pris ne peut pas dépasser montant_trouve."}
            )
        return data
