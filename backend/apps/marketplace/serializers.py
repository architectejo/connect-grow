from django.db.models import Count
from rest_framework import serializers

from apps.catalog import services as catalog_services
from apps.common.contexts import CONTEXT_USER
from apps.common.images import validate_image_pixels, validate_image_upload_size
from apps.common.serializers import PreloadingListSerializer
from apps.identity import services as identity_services
from apps.reviews import services as reviews_services
from apps.visibility import services as visibility_services

from . import services
from .models import ContactEvent, ExchangeProposal, Favorite, Offer, OfferImage


def _media_url(request, path):
    if not path:
        return None
    return request.build_absolute_uri(path) if request else path


class SellerSerializer(serializers.Serializer):
    """Fiche publique du vendeur, construite à partir d'identity.services.SellerSummary.
    Jamais de téléphone ni d'e-mail (règle 10, L0-10a-a)."""

    id = serializers.UUIDField()
    full_name = serializers.CharField()
    user_type = serializers.CharField()
    date_joined = serializers.DateTimeField()
    photo = serializers.SerializerMethodField()
    business_profile = serializers.SerializerMethodField()

    def get_photo(self, obj):
        return _media_url(self.context.get('request'), obj.photo)

    def get_business_profile(self, obj):
        if obj.business is None:
            return None
        return {
            'business_name': obj.business.business_name,
            'bio': obj.business.bio,
            'logo': _media_url(self.context.get('request'), obj.business.logo),
            'is_verified': obj.business.is_verified,
        }


class OfferImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferImage
        fields = ['id', 'image', 'order']


class OfferListSerializer(PreloadingListSerializer):
    pass


class OfferSerializer(serializers.ModelSerializer):
    """Contrat JSON historique conservé jusqu'à L0-11 : `post_type`, `category`, `commune`.
    Les données des autres domaines (catalogue, vendeur, tendance) sont chargées par lot
    pour toute la liste (`preload`), sans jointure ni requête par offre."""

    category = serializers.UUIDField(source='category_id')
    commune = serializers.UUIDField(source='commune_id')
    post_type = serializers.ChoiceField(source='offer_type', choices=Offer.OFFER_TYPE_CHOICES, required=False)
    category_name = serializers.SerializerMethodField()
    commune_name = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    seller_name = serializers.ReadOnlyField(source='seller.full_name')
    main_image = serializers.ImageField(
        required=False, allow_null=True, validators=[validate_image_upload_size, validate_image_pixels],
    )
    images = OfferImageSerializer(many=True, read_only=True)
    visibility_rank = serializers.SerializerMethodField()
    offer_rating = serializers.SerializerMethodField()
    seller_rating = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    favorites_count = serializers.SerializerMethodField()
    is_trending = serializers.SerializerMethodField()
    # Le Boost payant (lot 1) n'existe pas encore ; toujours False pour l'instant.
    is_sponsored = serializers.SerializerMethodField()
    allowed_channels = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            'id', 'seller', 'seller_name', 'category', 'category_name',
            'commune', 'commune_name', 'post_type', 'title', 'description',
            'price', 'currency', 'condition', 'stock', 'is_price_negotiable',
            'is_exchangeable', 'main_image', 'images', 'views_count',
            'likes_count', 'shares_count', 'created_at',
            'status', 'expires_at', 'visibility_score', 'visibility_rank',
            'offer_rating', 'seller_rating', 'is_favorited', 'favorites_count', 'is_trending', 'is_sponsored',
            'is_hidden_by_moderation', 'allowed_channels',
        ]
        read_only_fields = [
            'is_hidden_by_moderation', 'seller', 'views_count', 'likes_count', 'shares_count',
            'created_at', 'status', 'expires_at', 'visibility_score',
        ]
        list_serializer_class = OfferListSerializer

    def get_fields(self):
        """Troc désactivé : `is_exchangeable` est retiré du serializer, donc absent des réponses et
        ignoré en écriture (la valeur en base des offres existantes n'est pas modifiée)."""
        fields = super().get_fields()
        if 'exchange_enabled' not in self.context:
            self.context['exchange_enabled'] = services.is_exchange_enabled()
        if not self.context['exchange_enabled']:
            fields.pop('is_exchangeable', None)
        return fields

    CONTEXT_KEY = 'marketplace_preload'

    @classmethod
    def preload(cls, offers, context):
        """Charge par lot ce qui vient d'autres domaines ou d'agrégats : catégories et communes
        (catalog), vendeurs (identity), tendance (visibility), favoris. Les ids déjà connus
        ne sont pas relus."""
        cache = context.setdefault(cls.CONTEXT_KEY, {
            'categories': {}, 'communes': {}, 'sellers': {}, 'trending': set(), 'seen': set(),
            'favorite_counts': {}, 'favorited': set(), 'offer_ratings': {}, 'seller_ratings': {},
            'allowed_channels': {},
        })
        new = [o for o in offers if o.id not in cache['seen']]
        if not new:
            return
        ids = {o.id for o in new}

        missing_categories = {o.category_id for o in new} - cache['categories'].keys()
        missing_communes = {o.commune_id for o in new} - cache['communes'].keys()
        missing_sellers = {o.seller_id for o in new} - cache['sellers'].keys()
        cache['categories'].update(catalog_services.get_categories_by_ids(missing_categories))
        cache['communes'].update(catalog_services.get_communes_by_ids(missing_communes))
        cache['sellers'].update(identity_services.get_seller_summaries(missing_sellers))
        # Un id absent de son domaine est mémorisé pour ne pas être relu pour chaque offre.
        for key, wanted in (('categories', missing_categories), ('communes', missing_communes), ('sellers', missing_sellers)):
            for item_id in wanted:
                cache[key].setdefault(item_id, None)

        cache['trending'] |= visibility_services.trending_offer_ids(ids)
        counts = Favorite.objects.filter(offer_id__in=ids).values('offer_id').annotate(total=Count('id'))
        cache['favorite_counts'].update({row['offer_id']: row['total'] for row in counts})
        request = context.get('request')
        if request is not None and request.user.is_authenticated:
            cache['favorited'] |= set(
                Favorite.objects.filter(user=request.user, offer_id__in=ids).values_list('offer_id', flat=True)
            )
        # Notes affichées : calculées à la lecture, jamais stockées (ADR 0004). Deux requêtes pour
        # toute la liste ; `reviews` applique le seuil d'affichage.
        cache['offer_ratings'].update(reviews_services.get_offer_ratings(ids))
        cache['seller_ratings'].update(reviews_services.get_seller_ratings(
            CONTEXT_USER, {o.seller_id for o in new} - cache['seller_ratings'].keys(),
        ))
        # Canaux de contact ouverts (ADR 0005, C11) : une requête pour la page, jamais de numéro.
        missing_channels = {o.seller_id for o in new} - cache['allowed_channels'].keys()
        cache['allowed_channels'].update(identity_services.get_allowed_channels(missing_channels))
        cache['seen'] |= ids

    def _cache(self, obj):
        cache = self.context.get(self.CONTEXT_KEY)
        if cache is None or obj.id not in cache['seen']:
            # Objet isolé (ou hors liste préchargée) : chargement ciblé.
            self.preload([obj], self.context)
            cache = self.context[self.CONTEXT_KEY]
        return cache

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Le masquage par la modération n'est connu que du vendeur (L0-19).
        request = self.context.get('request')
        is_owner = request is not None and request.user.is_authenticated and request.user.id == instance.seller_id
        if not is_owner:
            data.pop('is_hidden_by_moderation', None)
        return data

    def get_seller(self, obj):
        summary = self._cache(obj)['sellers'].get(obj.seller_id)
        if summary is None:
            return None
        return SellerSerializer(summary, context=self.context).data

    @staticmethod
    def _rating(summary):
        # Objet toujours présent ; `average` est null sous le seuil d'affichage.
        if summary is None:
            return {'average': None, 'count': 0}
        return {'average': summary.average, 'count': summary.count}

    def get_offer_rating(self, obj):
        return self._rating(self._cache(obj)['offer_ratings'].get(obj.id))

    def get_seller_rating(self, obj):
        return self._rating(self._cache(obj)['seller_ratings'].get(obj.seller_id))

    def get_category_name(self, obj):
        category = self._cache(obj)['categories'].get(obj.category_id)
        return category.name if category else None

    def get_commune_name(self, obj):
        commune = self._cache(obj)['communes'].get(obj.commune_id)
        return commune.name if commune else None

    def validate(self, attrs):
        # CDC 3.2 : une offre porte au moins une photo (la principale).
        if self.instance is None and not attrs.get('main_image'):
            raise serializers.ValidationError({'main_image': "Une photo principale est requise."})
        return attrs

    def validate_category(self, value):
        if not catalog_services.category_exists(value):
            raise serializers.ValidationError("Catégorie introuvable.")
        return value

    def validate_commune(self, value):
        if not catalog_services.commune_exists(value):
            raise serializers.ValidationError("Commune introuvable.")
        return value

    def get_visibility_rank(self, obj):
        score = obj.visibility_score or 0.0
        if score > 50:
            return "Elite"
        if score > 10:
            return "Standard"
        return "Faible"

    def get_is_trending(self, obj):
        return obj.id in self._cache(obj)['trending']

    def get_allowed_channels(self, obj):
        # Aucun canal par défaut : seul `identity` dit ce que le vendeur a ouvert.
        return self._cache(obj)['allowed_channels'].get(obj.seller_id, [])

    def get_is_sponsored(self, obj):
        return False

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.id in self._cache(obj)['favorited']

    def get_favorites_count(self, obj):
        return self._cache(obj)['favorite_counts'].get(obj.id, 0)


class FavoriteListSerializer(PreloadingListSerializer):
    pass


class FavoriteSerializer(serializers.ModelSerializer):
    # Clés JSON `post` / `post_id` conservées jusqu'à L0-11.
    post = OfferSerializer(source='offer', read_only=True)
    post_id = serializers.PrimaryKeyRelatedField(
        source='offer', queryset=Offer.objects.filter(is_deleted=False, is_active=True, seller__is_active=True), write_only=True,
    )

    class Meta:
        model = Favorite
        fields = ['id', 'post', 'post_id', 'created_at']
        list_serializer_class = FavoriteListSerializer

    @classmethod
    def preload(cls, favorites, context):
        OfferSerializer.preload([f.offer for f in favorites], context)

    def validate(self, attrs):
        # Un même favori ne se crée pas deux fois (contrainte d'unicité en base).
        request = self.context['request']
        if Favorite.objects.filter(user=request.user, offer=attrs['offer']).exists():
            raise serializers.ValidationError("Cette annonce est déjà dans vos favoris.")
        return attrs


class _OfferMessageSerializer(serializers.ModelSerializer):
    """Base des demandes de contact et propositions d'échange (clé JSON `post` conservée)."""

    sender_name = serializers.ReadOnlyField(source='sender.full_name')
    post = serializers.PrimaryKeyRelatedField(source='offer', queryset=Offer.objects.filter(is_deleted=False))

    class Meta:
        fields = ['id', 'post', 'sender', 'sender_name', 'message', 'created_at']
        read_only_fields = ['sender']


class ContactEventSerializer(_OfferMessageSerializer):
    class Meta(_OfferMessageSerializer.Meta):
        model = ContactEvent
        fields = [*_OfferMessageSerializer.Meta.fields, 'channel']
        read_only_fields = [*_OfferMessageSerializer.Meta.read_only_fields, 'channel']
        # Le modèle accepte un message vide (CALL/WHATSAPP) ; ce point d'entrée ne crée que des MESSAGE.
        extra_kwargs = {'message': {'required': True, 'allow_blank': False}}


class ExchangeProposalSerializer(_OfferMessageSerializer):
    class Meta(_OfferMessageSerializer.Meta):
        model = ExchangeProposal


class RevealRequestSerializer(serializers.Serializer):
    """Corps de la révélation. `offer` reste une chaîne : un identifiant inconnu ou mal formé donne
    le même 404 uniforme que n'importe quelle offre indisponible (anti-énumération) ; le canal est
    validé par le service (400 `channel_invalid`)."""

    offer = serializers.CharField()
    channel = serializers.CharField(max_length=20)


class RevealResponseSerializer(serializers.Serializer):
    contact_event_id = serializers.UUIDField()
    channel = serializers.CharField()
    created = serializers.BooleanField()
    phone = serializers.CharField()
    tel_url = serializers.CharField(allow_null=True)
    whatsapp_url = serializers.CharField(allow_null=True)


class ReceivedRevealSerializer(serializers.Serializer):
    """Ligne de la liste vendeur : nom d'affichage et offre, jamais d'identifiant du visiteur ni de numéro."""

    id = serializers.UUIDField()
    channel = serializers.CharField()
    created_at = serializers.DateTimeField()
    requester_display_name = serializers.CharField()
    offer = serializers.SerializerMethodField()

    def get_offer(self, obj):
        return {'id': str(obj.offer_id), 'title': obj.offer_title}
