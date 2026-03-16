"""
Serializers API KONIS.
"""
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models import CustomUser, Entreprise, Lieu
from depenses.models import CategorieDepense, Depense
from inventaire.models import AchatMPSL, AchatUsine, MouvementStock, Stock, Transfert
from produits.models import Categorie, Produit
from usine.models import LotProduction, TransfertCession, TransfertInterUsine
from ventes.models import Facture, LigneFacture, LigneVente, Ticket, TicketReprint


# ---- Core ----
class LieuMinimalSerializer(serializers.ModelSerializer):
    type_lieu_display = serializers.CharField(source="get_type_lieu_display", read_only=True)

    class Meta:
        model = Lieu
        fields = ("id", "nom", "type_lieu", "type_lieu_display", "mouture_enabled")


class EntrepriseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entreprise
        fields = ("id", "nom", "created_at", "updated_at")


class LieuSerializer(serializers.ModelSerializer):
    entreprise_nom = serializers.CharField(source="entreprise.nom", read_only=True)
    type_lieu_display = serializers.CharField(source="get_type_lieu_display", read_only=True)
    code = serializers.CharField(max_length=20, allow_blank=True, required=False, default="")

    class Meta:
        model = Lieu
        fields = (
            "id",
            "entreprise",
            "entreprise_nom",
            "nom",
            "adresse",
            "code",
            "type_lieu",
            "is_active",
            "mouture_enabled",
            "type_lieu_display",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "entreprise": {"required": False, "allow_null": True},
        }

    def validate_code(self, value):
        if value is None:
            return ""
        return value.strip() if isinstance(value, str) else value


class UserMinimalSerializer(serializers.ModelSerializer):
    lieu = LieuMinimalSerializer(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = CustomUser
        fields = ("id", "username", "first_name", "last_name", "role", "role_display", "lieu", "entreprise")


class UserSerializer(serializers.ModelSerializer):
    lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.all(), allow_null=True, required=False)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "lieu",
            "entreprise",
            "is_active",
            "date_joined",
        )
        read_only_fields = ("date_joined",)
        extra_kwargs = {"password": {"write_only": True, "required": False}}

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user and request.user.entreprise_id:
            # Scoper le queryset lieu à l'entreprise de l'admin — évite l'IDOR cross-tenant
            fields["lieu"].queryset = Lieu.objects.filter(entreprise_id=request.user.entreprise_id)
        return fields

    def validate_username(self, value):
        qs = CustomUser.objects.filter(username__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Identifiant dÃ©jÃ  utilisÃ©.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["lieu"] = LieuMinimalSerializer(instance.lieu).data if instance.lieu else None
        return data

    def _validate_role_lieu(self, *, role, lieu):
        if role in (CustomUser.ROLE_ADMIN, CustomUser.ROLE_COMPTABLE):
            return
        if role == CustomUser.ROLE_BOUTIQUE:
            if not lieu:
                raise serializers.ValidationError({"lieu": "Un compte boutique doit être lié à un magasin."})
            if lieu.type_lieu != Lieu.TYPE_MAGASIN:
                raise serializers.ValidationError({"lieu": "Le lieu doit être de type magasin pour un compte boutique."})
            existing_qs = CustomUser.objects.filter(lieu=lieu)
            if self.instance:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            if existing_qs.exists():
                occupant = existing_qs.first()
                raise serializers.ValidationError({"lieu": f"Ce lieu est déjà attribué à '{occupant.username}'. Modifiez cet utilisateur ou créez un nouveau lieu."})
            return
        if role == CustomUser.ROLE_USINE:
            if not lieu:
                raise serializers.ValidationError({"lieu": "Un compte usine doit être lié à une usine."})
            if lieu.type_lieu != Lieu.TYPE_USINE:
                raise serializers.ValidationError({"lieu": "Le lieu doit être de type usine pour un compte usine."})
            existing_qs = CustomUser.objects.filter(lieu=lieu)
            if self.instance:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            if existing_qs.exists():
                occupant = existing_qs.first()
                raise serializers.ValidationError({"lieu": f"Ce lieu est déjà attribué à '{occupant.username}'. Modifiez cet utilisateur ou créez un nouveau lieu."})
            return
        if role == CustomUser.ROLE_MPSL:
            if not lieu:
                raise serializers.ValidationError({"lieu": "Un compte MPSL doit être lié à un dépôt MPSL."})
            if lieu.type_lieu != Lieu.TYPE_MPSL:
                raise serializers.ValidationError({"lieu": "Le lieu doit être de type MPSL pour un compte MPSL."})
            existing_qs = CustomUser.objects.filter(lieu=lieu)
            if self.instance:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            if existing_qs.exists():
                occupant = existing_qs.first()
                raise serializers.ValidationError({"lieu": f"Ce lieu est déjà attribué à '{occupant.username}'. Modifiez cet utilisateur ou créez un nouveau lieu."})
            return

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        self._validate_role_lieu(role=validated_data.get("role"), lieu=validated_data.get("lieu"))
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        self._validate_role_lieu(
            role=validated_data.get("role", instance.role),
            lieu=validated_data.get("lieu", instance.lieu),
        )
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class FactoryUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "username", "email", "first_name", "last_name", "is_active")


class FactorySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nom", read_only=True)
    address = serializers.CharField(source="adresse", read_only=True)
    user = FactoryUserSerializer(source="compte_boutique", read_only=True)

    class Meta:
        model = Lieu
        fields = (
            "id",
            "name",
            "address",
            "code",
            "is_active",
            "created_at",
            "updated_at",
            "user",
            "entreprise",
        )


class FactoryCreateSerializer(serializers.Serializer):
    entreprise_id = serializers.PrimaryKeyRelatedField(
        source="entreprise",
        queryset=Entreprise.objects.all(),
        required=False,
        allow_null=True,
    )
    factory_name = serializers.CharField(max_length=255)
    factory_address = serializers.CharField(required=False, allow_blank=True, default="")
    user_email = serializers.EmailField()
    user_first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    user_last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    user_password = serializers.CharField(write_only=True)

    def validate_factory_name(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Le nom d'usine est obligatoire.")
        exists = Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE, nom__iexact=normalized).exists()
        if exists:
            raise serializers.ValidationError("Une usine avec ce nom existe déjà.")
        return normalized

    def validate_user_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate_user_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class FactoryUpdateSerializer(serializers.Serializer):
    factory_name = serializers.CharField(max_length=255, required=False)
    factory_address = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    user_email = serializers.EmailField(required=False)
    user_first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    user_last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    user_password = serializers.CharField(required=False, write_only=True)

    def validate_factory_name(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("Le nom d'usine est obligatoire.")
        instance = self.context.get("instance")
        qs = Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE, nom__iexact=normalized)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Une usine avec ce nom existe déjà.")
        return normalized

    def validate_user_email(self, value):
        user = self.context.get("user")
        qs = CustomUser.objects.filter(email__iexact=value)
        if user is not None:
            qs = qs.exclude(pk=user.pk)
        if qs.exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate_user_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


# ---- Produits ----
class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = ("id", "nom", "created_at")


class ProduitMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produit
        fields = ("id", "nom", "code", "unite", "categorie", "category")


class ProduitSerializer(serializers.ModelSerializer):
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True)

    class Meta:
        model = Produit
        fields = ("id", "categorie", "categorie_nom", "nom", "code", "category", "unite", "created_at", "updated_at")


# ---- Inventaire ----
class StockSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_code = serializers.CharField(source="produit.code", read_only=True)
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)

    class Meta:
        model = Stock
        fields = ("id", "produit", "produit_nom", "produit_code", "lieu", "lieu_nom", "quantite")


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


# ---- Ventes ----
class LigneVenteSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = LigneVente
        fields = ("id", "produit", "produit_nom", "quantite", "prix_unitaire", "total")


class TicketSerializer(serializers.ModelSerializer):
    lignes = LigneVenteSerializer(many=True, read_only=True)
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)
    lignes_count = serializers.SerializerMethodField()
    mouture_source = serializers.SerializerMethodField()

    def get_lignes_count(self, obj):
        return len(obj.lignes.all())

    def get_mouture_source(self, obj):
        if not obj.mouture:
            return None
        return "mouture_seule" if self.get_lignes_count(obj) == 0 else "vente_avec_mouture"

    class Meta:
        model = Ticket
        fields = (
            "id", "lieu", "lieu_nom", "date", "numero", "lignes",
            # Mouture
            "produit_apporte", "mouture", "prix_mouture_kg", "prix_mouture_tonne", "prix_mouture_sac",
            "cout_mouture", "montant_total", "lignes_count", "mouture_source",
        )


class VenteBoutiqueCreateSerializer(serializers.Serializer):
    lignes = serializers.ListField(
        child=serializers.DictField(),
        help_text="[{produit: int, quantite: decimal, prix_unitaire: decimal}, ...]",
    )
    # Champs mouture (tous optionnels)
    mouture = serializers.BooleanField(default=False)
    prix_mouture_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        required=False, allow_null=True, default=None,
    )
    prix_mouture_tonne = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        required=False, allow_null=True, default=None,
    )
    prix_mouture_sac = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        required=False, allow_null=True, default=None,
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
        if data.get("mouture"):
            has_price = any(
                value is not None
                for value in (
                    data.get("prix_mouture_kg"),
                    data.get("prix_mouture_tonne"),
                    data.get("prix_mouture_sac"),
                )
            )
            if not has_price:
                raise serializers.ValidationError(
                    "Mouture demandée : au moins un prix (kg, tonne ou sac) est requis."
                )
        return data


class MoutureSeuleSerializer(serializers.Serializer):
    """Sérialiseur pour le service mouture-seule (sans achat de produits)."""
    quantite = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
        help_text="Quantité à moudre (ex: 50 pour 50 kg)"
    )
    unite = serializers.ChoiceField(
        choices=["kg", "tonne", "sac"],
        help_text="Unité de mesure : kg, tonne ou sac"
    )
    prix_unitaire = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"),
        help_text="Prix par unité (FCFA)"
    )
    produit_nom = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default="",
        help_text="Nom du produit apporté par le client (ex: Maïs, Manioc…)"
    )


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
    lieu = serializers.PrimaryKeyRelatedField(queryset=Lieu.objects.all(), required=False)
    client_nom = serializers.CharField(required=False, allow_blank=True, default="")
    client_contact = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lignes = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="[{produit: int?, description: str, quantite: decimal, prix_unitaire: decimal}]",
    )

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


class BoutiqueStockReceiptSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(source="produit", queryset=Produit.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        entreprise = getattr(getattr(request, "user", None), "entreprise", None)
        if entreprise:
            fields["product_id"].queryset = Produit.objects.filter(entreprise=entreprise)
        return fields


# ---- Dépenses ----
class CategorieDepenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieDepense
        fields = ("id", "nom", "created_at")


class DepenseSerializer(serializers.ModelSerializer):
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)
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
        )

    def validate_montant(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Le montant ne peut pas être négatif.")
        return value


    def validate_lieu(self, value):
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.entreprise_id:
            if value.entreprise_id != request.user.entreprise_id:
                raise serializers.ValidationError("Lieu hors de votre entreprise.")
        return value

# ---- Usine ----

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
        if entreprise:
            fields["produit_fini"].queryset = Produit.objects.filter(
                entreprise=entreprise, category=Produit.CATEGORY_FINISHED
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
    prix_par_sac = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))

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


# ---- AchatUsine simplifi ----

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


# ---- TransfertInterUsine ----

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


class TicketReprintCreateSerializer(serializers.Serializer):
    """Serializer pour enregistrer une réimpression de ticket."""
    motif = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")



# ---- MPSL ----

class AchatMPSLSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    produit_code = serializers.CharField(source="produit.code", read_only=True)
    lieu_nom = serializers.CharField(source="lieu.nom", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = AchatMPSL
        fields = (
            "id",
            "lieu",
            "lieu_nom",
            "produit",
            "produit_nom",
            "produit_code",
            "quantite",
            "unite",
            "prix_unitaire",
            "prix_total",
            "notes",
            "created_by",
            "created_by_username",
            "date",
        )
        read_only_fields = ("prix_total", "created_by", "date")


class AchatMPSLCreateSerializer(serializers.Serializer):
    lieu = serializers.PrimaryKeyRelatedField(
        queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_MPSL)
    )
    produit = serializers.PrimaryKeyRelatedField(queryset=Produit.objects.all())
    quantite = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unite = serializers.ChoiceField(choices=AchatMPSL.UNITE_CHOICES, default=AchatMPSL.UNITE_SACS)
    prix_unitaire = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user and request.user.entreprise_id:
            fields["produit"].queryset = Produit.objects.filter(
                entreprise_id=request.user.entreprise_id
            )
            fields["lieu"].queryset = Lieu.objects.filter(
                type_lieu=Lieu.TYPE_MPSL,
                entreprise_id=request.user.entreprise_id,
            )
        return fields


class TransfertMPSLCreateSerializer(serializers.Serializer):
    """Transfert depuis MPSL vers usine ou magasin (mouvement pur, sans prix)."""
    from_lieu = serializers.PrimaryKeyRelatedField(
        queryset=Lieu.objects.filter(type_lieu=Lieu.TYPE_MPSL)
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
                type_lieu=Lieu.TYPE_MPSL,
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
