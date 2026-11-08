from django.urls import reverse
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.catalog import services as catalog_services
from apps.common.serializers import PreloadingListSerializer

from .models import KycDocument, OtpCode, User, normalize_email, phone_validator
from .permissions import REVIEW_KYC_PERMISSION
from .services import validate_new_password


OTP_REJECTED = "Code invalide ou expiré."


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


class UserSerializer(CityCommuneNamesMixin, serializers.ModelSerializer):
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
            'ville',
            'ville_name',
            'commune',
            'commune_name',
            'phone',
            'phone_verified',
            'password',
            'otp_code',
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
        """Crée le compte. Un compte est unique (ADR 0006, règle 1) : il n'y a plus de type de compte ni de profil
        entreprise à l'inscription. Compatibilité transitoire : `user_type` et `business_profile`, s'ils sont
        encore envoyés par un ancien client, ne sont pas lus (aucun effet, aucune organisation créée) ; une
        organisation se crée ensuite par `POST organizations/`."""
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

        return user


    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if self._phone_just_verified:
            instance.phone_verified = True
        instance.save()
        return instance


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
    # Lecture seule (file de vérification, décision) : aucun chemin de stockage n'est jamais renvoyé.
    download_url = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

    class Meta:
        model = KycDocument
        fields = [
            'id', 'document_type', 'download_url', 'status', 'rejection_reason',
            'created_at', 'reviewed_at', 'organization',
        ]
        read_only_fields = ['id', 'status', 'rejection_reason', 'created_at', 'reviewed_at']

    def get_organization(self, obj):
        """Organisation concernée (file de vérification) : identifiant, nom, type. Aucune coordonnée de membre."""
        if obj.organization_id is None:
            return None
        organization = obj.organization
        return {'id': str(organization.pk), 'name': organization.name, 'org_type': organization.org_type}

    def get_download_url(self, obj):
        """URL de l'endpoint authentifié, pour les seuls examinateurs habilités."""
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user.has_perm(REVIEW_KYC_PERMISSION):
            return reverse('kyc_download', args=[obj.pk])
        return None


class OrganizationKycDocumentSerializer(serializers.ModelSerializer):
    """Pièce d'une organisation vue par ses membres (ADR 0006, 9.4) : jamais d'URL ni de contenu de fichier."""

    document_type_label = serializers.CharField(source='get_document_type_display', read_only=True)
    uploaded_at = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = KycDocument
        fields = ['id', 'document_type', 'document_type_label', 'status', 'rejection_reason', 'uploaded_at', 'reviewed_at']
        read_only_fields = fields
