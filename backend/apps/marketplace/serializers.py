from rest_framework import serializers
from apps.catalog import services as catalog_services
from apps.common.serializers import PreloadingListSerializer

from .models import Favorite, Post, PostImage


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.identity.models import BusinessProfile
        model = BusinessProfile
        fields = ['business_name', 'bio', 'logo', 'is_verified']

class SellerSerializer(serializers.ModelSerializer):
    business_profile = BusinessProfileSerializer(read_only=True)
    trust_score = serializers.SerializerMethodField()
    reviews_count = serializers.IntegerField(read_only=True)
    is_new_seller = serializers.SerializerMethodField()
    is_trusted_seller = serializers.SerializerMethodField()

    class Meta:
        from apps.identity.models import User
        model = User
        fields = [
            'id', 'full_name', 'photo', 'phone', 'user_type', 'business_profile', 'date_joined',
            'trust_score', 'reviews_count', 'is_new_seller', 'is_trusted_seller',
        ]

    def _min_reviews_to_display(self):
        from apps.reputation.models import TrustScoreSettings
        return TrustScoreSettings.get_solo().min_reviews_to_display

    def get_is_new_seller(self, obj):
        # CDC 3.7 : le score n'est affiché publiquement qu'à partir de 3 avis.
        return obj.reviews_count < self._min_reviews_to_display()

    def get_trust_score(self, obj):
        if self.get_is_new_seller(obj):
            return None
        return obj.trust_score

    def get_is_trusted_seller(self, obj):
        # CDC 3.8 : badge « Vendeur fiable » (Trust Score >= 4.5, au moins 10 avis).
        return obj.trust_score >= 4.5 and obj.reviews_count >= 10


class PostImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ['id', 'image', 'order']


class PostListSerializer(PreloadingListSerializer):
    pass


class PostSerializer(serializers.ModelSerializer):
    # Clés JSON `category` / `commune` conservées : UUID du domaine catalog. Les noms
    # sont lus par lot dans le catalogue (plus de jointure ORM entre domaines).
    category = serializers.UUIDField(source='category_id')
    commune = serializers.UUIDField(source='commune_id')
    category_name = serializers.SerializerMethodField()
    commune_name = serializers.SerializerMethodField()
    seller = SellerSerializer(read_only=True)
    seller_name = serializers.ReadOnlyField(source='seller.full_name')
    main_image = serializers.ImageField(required=False, allow_null=True)
    images = PostImageSerializer(many=True, read_only=True)
    visibility_rank = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    favorites_count = serializers.IntegerField(source='favorited_by.count', read_only=True)
    is_trending = serializers.SerializerMethodField()
    # CDC 3.8 : le Boost (billing, P3) n'existe pas encore ; toujours False pour l'instant.
    is_sponsored = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'seller', 'seller_name', 'category', 'category_name',
            'commune', 'commune_name', 'post_type', 'title', 'description',
            'price', 'currency', 'condition', 'stock', 'is_price_negotiable',
            'is_exchangeable', 'main_image', 'images', 'views_count',
            'likes_count', 'comments_count', 'shares_count', 'created_at',
            'status', 'expires_at', 'visibility_score', 'visibility_rank',
            'is_favorited', 'favorites_count', 'is_trending', 'is_sponsored',
        ]
        read_only_fields = [
            'seller', 'views_count', 'likes_count', 'comments_count', 'shares_count',
            'created_at', 'status', 'expires_at', 'visibility_score',
        ]
        list_serializer_class = PostListSerializer

    CATALOG_CONTEXT_KEY = 'marketplace_catalog'

    @classmethod
    def preload(cls, posts, context):
        """Charge en deux requêtes les catégories et communes des annonces données,
        et les ajoute au cache du contexte (les ids déjà connus ne sont pas relus)."""
        cache = context.setdefault(cls.CATALOG_CONTEXT_KEY, {'categories': {}, 'communes': {}})
        missing_categories = {p.category_id for p in posts} - cache['categories'].keys()
        missing_communes = {p.commune_id for p in posts} - cache['communes'].keys()
        cache['categories'].update(catalog_services.get_categories_by_ids(missing_categories))
        cache['communes'].update(catalog_services.get_communes_by_ids(missing_communes))
        # Un id absent du catalogue est mémorisé pour ne pas être relu pour chaque annonce.
        for category_id in missing_categories:
            cache['categories'].setdefault(category_id, None)
        for commune_id in missing_communes:
            cache['communes'].setdefault(commune_id, None)

    def _catalog(self, obj):
        cache = self.context.get(self.CATALOG_CONTEXT_KEY)
        if (
            cache is None
            or obj.category_id not in cache['categories']
            or obj.commune_id not in cache['communes']
        ):
            # Objet isolé (ou hors liste préchargée) : chargement ciblé.
            self.preload([obj], self.context)
            cache = self.context[self.CATALOG_CONTEXT_KEY]
        return cache

    def get_category_name(self, obj):
        category = self._catalog(obj)['categories'].get(obj.category_id)
        return category.name if category else None

    def get_commune_name(self, obj):
        commune = self._catalog(obj)['communes'].get(obj.commune_id)
        return commune.name if commune else None

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
        if score > 50: return "Elite"
        if score > 10: return "Standard"
        return "Faible"

    def get_is_trending(self, obj):
        return obj.is_trending()

    def get_is_sponsored(self, obj):
        return False

    def get_is_favorited(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        # Nécessite d'annoter/prefetch pour éviter le N+1 sur les listes (voir la vue).
        if hasattr(obj, 'is_favorited_by_user'):
            return obj.is_favorited_by_user
        return obj.favorited_by.filter(user=request.user).exists()


class FavoriteListSerializer(PreloadingListSerializer):
    pass


class FavoriteSerializer(serializers.ModelSerializer):
    post = PostSerializer(read_only=True)
    post_id = serializers.PrimaryKeyRelatedField(
        source='post', queryset=Post.objects.filter(is_delete=False), write_only=True,
    )

    class Meta:
        model = Favorite
        fields = ['id', 'post', 'post_id', 'created_at']
        list_serializer_class = FavoriteListSerializer

    @classmethod
    def preload(cls, favorites, context):
        PostSerializer.preload([f.post for f in favorites], context)
