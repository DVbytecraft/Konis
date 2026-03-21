from rest_framework import serializers

from produits.models import Categorie, Produit


class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = ("id", "nom", "created_at", "entreprise")
        read_only_fields = ("entreprise",)


class ProduitMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = ("id", "nom", "code", "unite", "categorie", "category")


class ProduitSerializer(serializers.ModelSerializer):
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True)

    class Meta:
        model = Produit
        fields = ("id", "categorie", "categorie_nom", "nom", "code", "category", "unite", "created_at", "updated_at")
