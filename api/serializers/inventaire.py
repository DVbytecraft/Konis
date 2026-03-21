from decimal import Decimal

from rest_framework import serializers

from core.models import Lieu
from inventaire.models import MouvementStock, Stock, Transfert
from produits.models import Produit


class StockSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_code = serializers.CharField(source="produit.code", read_only=True)
    produit_unite = serializers.CharField(source="produit.unite", read_only=True)
    poids_par_sac = serializers.DecimalField(
        source="produit.poids_par_sac", max_digits=10, decimal_places=3,
        read_only=True, allow_null=True,
    )
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)

    class Meta:
        model = Stock
        fields = (
            "id", "produit", "produit_nom", "produit_code", "produit_unite",
            "poids_par_sac", "lieu", "lieu_nom", "quantite", "quantite_kg",
        )


class MouvementStockSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    production_order_nom = serializers.CharField(source="production_order.nom_lot", read_only=True)

    class Meta:
        model = MouvementStock
        fields = ("id", "produit", "produit_nom", "quantite", "unit_price", "production_order", "production_order_nom")


class TransfertSerializer(serializers.ModelSerializer):
    mouvements = MouvementStockSerializer(many=True, read_only=True)
    from_lieu_nom = serializers.CharField(source="from_lieu.nom", read_only=True)
    to_lieu_nom = serializers.CharField(source="to_lieu.nom", read_only=True)

    class Meta:
        model = Transfert
        fields = ("id", "from_lieu", "from_lieu_nom", "to_lieu", "to_lieu_nom", "date", "mouvements")


class TransfertCreateSerializer(serializers.Serializer):
    from_lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.all())
    to_lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.all())
    lignes = serializers.ListField(
        child=serializers.DictField(),
        help_text="[{produit_id: int, quantite: decimal}, ...]",
    )

    def validate_lignes(self, value):
        for item in value:
            if "produit" not in item or "quantite" not in item:
                raise serializers.ValidationError("Chaque ligne doit avoir produit et quantite.")
            try:
                quantite = Decimal(str(item["quantite"]))
            except Exception:
                raise serializers.ValidationError("quantite doit être un nombre valide.")
            if quantite <= 0:
                raise serializers.ValidationError("Quantité doit être > 0.")
            if "unit_price" in item and Decimal(str(item["unit_price"])) < 0:
                raise serializers.ValidationError("unit_price doit être >= 0.")
        return value


class BoutiqueStockReceiptSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(source="produit", queryset=Produit.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        entreprise = getattr(getattr(request, "user", None), "entreprise", None)
        # Fail-safe : .none() si pas d'entreprise — évite IDOR cross-tenant
        fields["product_id"].queryset = (
            Produit.objects.filter(entreprise=entreprise)
            if entreprise
            else Produit.objects.none()
        )
        return fields
