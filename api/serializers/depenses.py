from rest_framework import serializers

from depenses.models import CategorieDepense, Depense


class CategorieDepenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieDepense
        fields = ("id", "nom", "created_at", "entreprise")
        read_only_fields = ("entreprise",)


class DepenseSerializer(serializers.ModelSerializer):
    lieu_nom = serializers.SerializerMethodField()
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True)
    production_order_nom = serializers.CharField(source="production_order.nom_lot", read_only=True)

    class Meta:
        model = Depense
        fields = (
            "id",
            "lieu",
            "lieu_nom",
            "categorie",
            "categorie_nom",
            "production_order",
            "production_order_nom",
            "montant",
            "date",
            "libelle",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
        extra_kwargs = {
            "lieu": {"required": False, "allow_null": True},
        }

    def get_lieu_nom(self, obj):
        return obj.lieu.nom if obj.lieu_id else "Autre"

    def validate_montant(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Le montant ne peut pas être négatif.")
        return value

    def validate_lieu(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.entreprise_id:
            if value.entreprise_id != request.user.entreprise_id:
                raise serializers.ValidationError("Lieu hors de votre entreprise.")
        return value

    def validate_categorie(self, value):
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.entreprise_id:
            if value.entreprise_id != request.user.entreprise_id:
                raise serializers.ValidationError("Catégorie hors de votre entreprise.")
        return value
