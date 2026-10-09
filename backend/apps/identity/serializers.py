from django.conf import settings
from django.urls import reverse
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.catalog import services as catalog_services
from apps.common.serializers import PreloadingListSerializer

from .models import BusinessProfile, KycDocument, OtpCode, User, normalize_email, phone_validator
from .kyc_files import validate_kyc_file
from .permissions import REVIEW_KYC_PERMISSION
from .services import validate_new_password


OTP_REJECTED = "Code invalide ou expiré."


class BusinessProfileSerializer(serializers.ModelSerializer):
    # Clé JSON `categories` conservée : liste d'UUID de catégories (domaine catalog).
    categories = serializers.ListField(child=serializers.UUIDField(), source='category_ids', required=False)

    class Meta:
        model = BusinessProfile
        fields = ['business_name', 'categories', 'bio', 'logo', 'nif', 'is_verified']
        # is_verified ne se décide que par la validation KYC de la modération
        # (KycDecisionView), jamais par l'utilisateur via son propre profil (CDC 3.1).
        read_only_fields = ['is_verified']

    def validate_categories(self, value):
        unknown = set(value) - catalog_services.existing_category_ids(value)
        if unknown:
            raise serializers.ValidationError("Catégorie introuvable.")
        return value


class CityCommuneNamesMixin:
    """Noms de ville et de commune lus par lot dans le catalogue (plus de jointure ORM)."""

    CATALOG_CONTEXT_KEY = 'identity_catalog'

    @classmethod
    def preload(cls, users, context):
        context[cls.CATALOG_CONTEXT_KEY] = {
            'cities': catalog_services.get_cities_by_ids(u.city_id for u in users if u.city_id),
            'communes': catalog_services.get_communes_by_ids(u.commune_id for u in users if u.commune_id),
        }

    def _catalog(self, obj):
        cache = self.context.get(self.CATALOG_CONTEXT_KEY)
        if cache is None:
            self.preload([obj], self.context)
            cache = self.context[self.CATALOG_CONTEXT_KEY]
        return cache

    def get_ville_name(self, obj):
        city = self._catalog(obj)['cities'].get(obj.city_id)
        return city.name if city else None

    def get_commune_name(self, obj):
        commune = self._catalog(obj)['communes'].get(obj.commune_id)
        return commune.name if commune else None


class UserListSerializer(PreloadingListSerializer):
    pass


class PublicBusinessSerializer(CityCommuneNamesMixin, serializers.ModelSerializer):
    """Fiche publique d'une entreprise : liste blanche stricte (règle 10).
    Jamais d'e-mail, de téléphone, de NIF ni de date d'inscription."""

    business_name = serializers.CharField(source='business_profile.business_name', read_only=True)
    logo = serializers.ImageField(source='business_profile.logo', read_only=True)
    bio = serializers.CharField(source='business_profile.bio', read_only=True)
    categories = serializers.ListField(
        child=serializers.UUIDField(), source='business_profile.category_ids', read_only=True,
    )
    is_verified = serializers.BooleanField(source='business_profile.is_verified', read_only=True)
    ville_name = serializers.SerializerMethodField()
    commune_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'business_name', 'logo', 'bio', 'categories', 'ville_name', 'commune_name', 'is_verified',
        ]
        read_only_fields = fields
        list_serializer_class = UserListSerializer


class UserSerializer(CityCommuneNamesMixin, serializers.ModelSerializer):
    # Inclusion du profil entreprise (imbriqué)
    business_profile = BusinessProfileSerializer(required=False)
    # Clés JSON `ville` / `commune` conservées (UUID du domaine catalog).
    ville = serializers.UUIDField(source='city_id', required=False, allow_null=True)
    commune = serializers.UUIDField(source='commune_id', required=False, allow_null=True)
    ville_name = serializers.SerializerMethodField()
    commune_name = serializers.SerializerMethodField()
    # E-mail déclaré à la main (pas d'UniqueValidator du modèle, sensible à la casse) : l'unicité
    # insensible à la casse est contrôlée dans validate_email sur la forme normalisée.
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True, max_length=254)
    # Fourni uniquement lors d'une inscription/modification par téléphone (CDC 3.1) ;
    # ce n'est pas un champ du modèle, il est retiré dans validate().
    otp_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'photo',
            'full_name',
            'user_type',
            'ville',
            'ville_name',
            'commune',
            'commune_name',
            'phone',
            'phone_verified',
            'password',
            'otp_code',
            'business_profile',
            'date_joined'
        ]
        extra_kwargs = {
            'password': {'write_only': True},  # Sécurité : ne jamais renvoyer le mot de passe
            'phone_verified': {'read_only': True},
            # Pas d'UniqueValidator sur le téléphone : il dirait qui est inscrit (oracle
            # d'existence). L'unicité est contrôlée dans validate(), APRÈS la preuve de
            # possession du numéro par OTP, avec une réponse neutre. Le format reste vérifié.
            'phone': {'validators': [phone_validator]},
        }
        list_serializer_class = UserListSerializer

    def validate_email(self, value):
        email = normalize_email(value)
        if email:
            others = User.objects.filter(email__iexact=email)
            if self.instance is not None:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise serializers.ValidationError("Un utilisateur avec cette adresse e-mail existe déjà.")
        return email

    def validate_password(self, value):
        if self.instance is not None:
            return value  # refusé dans validate() : le mot de passe ne se change pas ici
        data = getattr(self, 'initial_data', {})
        candidate = User(
            email=data.get('email') or None, phone=data.get('phone') or None,
            full_name=data.get('full_name') or '',
        )
        validate_new_password(value, candidate)
        return value

    def validate_ville(self, value):
        if value is not None and not catalog_services.city_exists(value):
            raise serializers.ValidationError("Ville introuvable.")
        return value

    def validate_commune(self, value):
        if value is not None and not catalog_services.commune_exists(value):
            raise serializers.ValidationError("Commune introuvable.")
        return value

    def validate(self, attrs):
        """Si un téléphone est fourni (à la création ou pour le changer), il doit
        être accompagné d'un code OTP valide (purpose=REGISTER) — CDC 3.1."""
        if self.instance is not None and 'password' in attrs:
            # Le mot de passe ne se change que par /change-password/ (ancien mot de passe
            # exigé) ou par la réinitialisation OTP, jamais par la mise à jour du profil.
            raise serializers.ValidationError(
                {'password': "Utilisez « Changer le mot de passe » pour modifier votre mot de passe."}
            )

        if self.instance is not None:
            # Le type de compte se choisit à l'inscription ; il est en lecture seule ensuite
            # (la valeur envoyée est ignorée, comme tout champ en lecture seule).
            attrs.pop('user_type', None)

        # Vides normalisés en NULL (l'unicité ne porte que sur les valeurs renseignées).
        for field in ('email', 'phone'):
            if field in attrs and not attrs[field]:
                attrs[field] = None
        if self.instance is None and not attrs.get('email') and not attrs.get('phone'):
            raise serializers.ValidationError("Un e-mail ou un numéro de téléphone est obligatoire.")

        self._validate_city_and_commune(attrs)

        phone = attrs.get('phone')
        otp_code = attrs.pop('otp_code', None)

        self._phone_just_verified = False
        # Un numéro inchangé (PATCH /me/ qui renvoie le même numéro) ne redemande pas d'OTP.
        phone_unchanged = self.instance is not None and phone == self.instance.phone
        if phone and not phone_unchanged:
            if not otp_code:
                raise serializers.ValidationError(
                    {'otp_code': "Un code de vérification est requis pour ce numéro de téléphone."}
                )
            otp = (
                OtpCode.objects.filter(phone=phone, purpose=OtpCode.PURPOSE_REGISTER, is_used=False)
                .order_by('-created_at')
                .first()
            )
            if not otp or not otp.verify(otp_code):
                raise serializers.ValidationError({'otp_code': OTP_REJECTED})
            # Numéro déjà pris : même réponse que pour un code faux (aucune confirmation
            # d'existence). Un OTP REGISTER n'est émis que pour un numéro libre ; ce cas
            # ne survient donc qu'en course ou par un code obtenu avant l'inscription d'un autre.
            others = User.objects.filter(phone=phone)
            if self.instance is not None:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise serializers.ValidationError({'otp_code': OTP_REJECTED})
            self._phone_just_verified = True

        return attrs

    def _validate_city_and_commune(self, attrs):
        """La commune doit appartenir à la ville (vérifié via catalog.services) et une
        commune exige une ville. En mise à jour partielle, les valeurs actuelles complètent."""
        if 'city_id' not in attrs and 'commune_id' not in attrs:
            return
        current_city = self.instance.city_id if self.instance else None
        current_commune = self.instance.commune_id if self.instance else None
        city_id = attrs['city_id'] if 'city_id' in attrs else current_city
        commune_id = attrs['commune_id'] if 'commune_id' in attrs else current_commune
        if commune_id and not city_id:
            raise serializers.ValidationError({'ville': "Indiquez la ville de la commune."})
        if commune_id and not catalog_services.commune_belongs_to_city(commune_id, city_id):
            raise serializers.ValidationError({'commune': "Cette commune n'appartient pas à la ville choisie."})

    def create(self, validated_data):
        """
        Crée un utilisateur et son profil entreprise si le type est 'ENTREPRISE'.
        """
        business_data = validated_data.pop('business_profile', None)

        # Utilise create_user du UserManager pour hacher le mot de passe
        try:
            with transaction.atomic():
                user = User.objects.create_user(**validated_data)
        except IntegrityError:
            # Course sur un téléphone déjà pris : réponse neutre. (Un e-mail déjà pris est
            # signalé par l'UniqueValidator, dette tracée dans l'ADR 0002.)
            raise serializers.ValidationError({'otp_code': OTP_REJECTED})

        if self._phone_just_verified:
            user.phone_verified = True
            user.save(update_fields=['phone_verified'])

        if user.user_type == 'ENTREPRISE' and business_data:
            category_ids = business_data.pop('category_ids', None)
            profile = BusinessProfile.objects.create(user=user, **business_data)
            if category_ids:
                profile.set_category_ids(category_ids)

        return user


    # Dans UserSerializer.update
    def update(self, instance, validated_data):
        business_data = validated_data.pop('business_profile', None)

        # Mise à jour User
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if self._phone_just_verified:
            instance.phone_verified = True
        instance.save()

        # Mise à jour Profil
        if instance.user_type == 'ENTREPRISE' and business_data:
            category_ids = business_data.pop('category_ids', None)
            business_profile, _ = BusinessProfile.objects.get_or_create(user=instance)
            for attr, value in business_data.items():
                # Si value est None ou vide et que c'est une image,
                # on vérifie si on veut vraiment l'écraser
                setattr(business_profile, attr, value)
            business_profile.save()
            if category_ids is not None:
                business_profile.set_category_ids(category_ids)

        return instance

    def to_representation(self, instance):
        """
        S'assure que business_profile est null dans la réponse JSON
        si l'utilisateur n'est pas de type ENTREPRISE.
        """
        data = super().to_representation(instance)
        try:
            # Vérifie si le profil existe réellement
            if not hasattr(instance, 'business_profile'):
                data['business_profile'] = None
        except BusinessProfile.DoesNotExist:
            data['business_profile'] = None
        return data


class IdentifierTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Connexion par e-mail OU par téléphone (CDC 3.1), au choix. Remplace la
    validation par défaut de SimpleJWT (qui n'accepte que USERNAME_FIELD) sans
    passer par authenticate()/ModelBackend, qui suppose un email toujours présent."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields['phone'] = serializers.CharField(required=False)

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        phone = attrs.get('phone')
        password = attrs.get('password')

        if not password or (not email and not phone):
            raise serializers.ValidationError("email (ou phone) et password sont requis.")

        if email:
            email = normalize_email(email)
            user = User.objects.filter(email=email).first() or (
                User.objects.filter(email__iexact=email).order_by('date_joined').first() if email else None
            )
        else:
            user = User.objects.filter(phone=phone).first()
        if user is None or not user.is_active or not user.check_password(password):
            raise AuthenticationFailed(
                "Aucun compte actif trouvé avec les identifiants fournis.", 'no_active_account'
            )

        refresh = self.get_token(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class KycDocumentSerializer(serializers.ModelSerializer):
    # Le fichier n'est qu'en écriture : aucun chemin de stockage n'est jamais renvoyé.
    file = serializers.FileField(write_only=True, validators=[validate_kyc_file])
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = KycDocument
        fields = [
            'id', 'document_type', 'file', 'download_url', 'status', 'rejection_reason',
            'created_at', 'reviewed_at',
        ]
        read_only_fields = ['id', 'status', 'rejection_reason', 'created_at', 'reviewed_at']

    def get_download_url(self, obj):
        """URL de l'endpoint authentifié, pour les seuls examinateurs habilités."""
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user.has_perm(REVIEW_KYC_PERMISSION):
            return reverse('kyc_download', args=[obj.pk])
        return None

    def validate(self, attrs):
        if self.instance is not None:
            return attrs
        user = self.context['request'].user
        try:
            profile = user.business_profile
        except BusinessProfile.DoesNotExist:
            raise serializers.ValidationError("Un profil Business est requis avant de soumettre des pièces KYC.")
        existing = KycDocument.objects.filter(business_profile=profile)
        if existing.count() >= settings.KYC_MAX_DOCUMENTS_PER_PROFILE:
            raise serializers.ValidationError(
                "Nombre maximal de pièces atteint. Supprimez une pièce refusée avant d'en déposer une autre."
            )
        if existing.filter(
            document_type=attrs['document_type'],
            status__in=[KycDocument.STATUS_EN_ATTENTE, KycDocument.STATUS_VALIDE],
        ).exists():
            raise serializers.ValidationError(
                {'document_type': "Une pièce de ce type est déjà en attente ou validée."}
            )
        return attrs
