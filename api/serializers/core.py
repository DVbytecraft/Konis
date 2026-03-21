from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models import CustomUser, Entreprise, Lieu


class LieuMinimalSerializer(serializers.ModelSerializer):
    type_lieu_display = serializers.CharField(source="get_type_lieu_display", read_only=True)

    class Meta:
        model = Lieu
        fields = ("id", "nom", "type_lieu", "type_lieu_display", "mouture_enabled",
                  "prix_mouture_defaut", "prix_mouture_max")


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
        user = getattr(request, "user", None)
        entreprise_id = getattr(user, "entreprise_id", None)
        # Fail-safe : .none() si pas d'entreprise identifiée — évite IDOR cross-tenant
        fields["lieu"].queryset = (
            Lieu.objects.filter(entreprise_id=entreprise_id)
            if entreprise_id
            else Lieu.objects.none()
        )
        return fields

    def validate_username(self, value):
        qs = CustomUser.objects.filter(username__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Identifiant déjà utilisé.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["lieu"] = LieuMinimalSerializer(instance.lieu).data if instance.lieu else None
        return data

    def _validate_role_lieu(self, *, role, lieu):
        # Vérification cross-tenant : le lieu doit appartenir à l'entreprise de l'admin
        request = self.context.get("request")
        user_ent_id = getattr(getattr(request, "user", None), "entreprise_id", None)
        if lieu and user_ent_id and lieu.entreprise_id != user_ent_id:
            raise serializers.ValidationError({"lieu": "Lieu hors de votre entreprise."})

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
            # Lieu optionnel pour MPSL — l'utilisateur opère sur tout dépôt MPSL de son entreprise.
            if lieu and lieu.type_lieu != Lieu.TYPE_MPSL:
                raise serializers.ValidationError({"lieu": "Si un lieu est fourni, il doit être de type MPSL."})
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
