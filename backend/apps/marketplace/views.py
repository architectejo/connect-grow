import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.catalog import services as catalog_services
from apps.common.images import validate_image_pixels, validate_image_upload_size
from apps.common.pagination import OptionalPagination
from apps.common.throttles import ActionScopedThrottleMixin, AnonymousOrUserScopedThrottle, AnonymousScopedThrottle
from apps.moderation.permissions import can_moderate
from apps.moderation.services import record_audit
from apps.common.utils import parse_uuid
from apps.visibility import services as visibility_services

from . import services
from .models import ContactEvent, ExchangeProposal, Favorite, Offer, OfferImage
from .permissions import IsOfferOwner
from .serializers import (
    ContactEventSerializer, ExchangeProposalSerializer, FavoriteSerializer, OfferImageSerializer,
    OfferSerializer,
)

PRICE_LIMIT = Decimal('99999999.99')  # borne de Offer.price (10 chiffres dont 2 décimales)


def parse_price(value):
    """Prix de filtre borné à la plage du champ ; None si la valeur n'est pas un nombre."""
    try:
        price = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None
    if not price.is_finite():
        return None
    return max(-PRICE_LIMIT, min(PRICE_LIMIT, price)).quantize(Decimal('0.01'))


ANON_COOKIE = 'anon_id'
ANON_COOKIE_SALT = 'marketplace.anon_view'


def read_anon_id(request):
    """Identifiant de visiteur anonyme lu dans le cookie SIGNÉ par le serveur ; None si absent,
    falsifié ou expiré (la vue n'est alors pas comptée, un nouveau cookie est émis)."""
    value = request.COOKIES.get(ANON_COOKIE)
    if not value:
        return None
    try:
        return signing.loads(value, salt=ANON_COOKIE_SALT, max_age=settings.ANON_VIEW_COOKIE_MAX_AGE)
    except signing.BadSignature:
        return None


class OfferViewSet(ActionScopedThrottleMixin, viewsets.ModelViewSet):
    serializer_class = OfferSerializer
    pagination_class = OptionalPagination

    # Actions réservées au vendeur : elles portent aussi sur des offres inactives (pause,
    # expirée, corbeille), donc hors du queryset public.
    OWNER_ACTIONS = {
        'update', 'partial_update', 'destroy', 'soft_delete', 'restore', 'hard_delete',
        'pause', 'unpause', 'mark_sold', 'renew', 'images', 'delete_image',
    }
    throttle_scopes = {
        'list': ('offer_list', AnonymousOrUserScopedThrottle),
        'create': 'offer_upload', 'update': 'offer_upload', 'partial_update': 'offer_upload',
        'images': 'offer_upload', 'share': 'share', 'favorite': 'favorite',
        'retrieve': ('offer_view_anon', AnonymousScopedThrottle),
    }
    ORDERINGS = ('-visibility_score', 'visibility_score', '-created_at', 'created_at', 'price', '-price')

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        if self.action in self.OWNER_ACTIONS:
            return [permissions.IsAuthenticated(), IsOfferOwner()]
        if self.action == 'recalculate_all_scores':
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if self.action in self.OWNER_ACTIONS:
            # Filtré sur le vendeur : l'offre d'un autre répond 404, comme une offre inconnue.
            return Offer.objects.filter(seller=self.request.user).select_related('seller').prefetch_related('images')

        # On trie par le score de visibilité organique (E x R, ADR 0004) par défaut
        ordering = self.request.query_params.get('ordering', '-visibility_score')
        if ordering not in self.ORDERINGS:
            ordering = '-visibility_score'

        # Par défaut (Marketplace), on ne montre que ce qui n'est pas supprimé et actif
        # Les offres d'un vendeur suspendu ou banni (compte inactif) ne sont plus publiques.
        queryset = Offer.objects.filter(is_active=True, is_deleted=False, seller__is_active=True)

        # Filtre pour récupérer les offres de l'utilisateur connecté
        my_offers = self.request.query_params.get('my_posts')
        if self.action == 'retrieve' and self.request.user.is_authenticated:
            # Le vendeur retrouve toutes ses offres (pause, vendue, expirée, masquée par la
            # modération, corbeille) ; le public et les tiers restent limités aux offres actives.
            # Même requête SQL : seule la clause WHERE change.
            visible = Q(is_active=True, is_deleted=False, seller__is_active=True) | Q(seller=self.request.user)
            if can_moderate(self.request.user):
                # La modération consulte aussi les offres d'un vendeur sanctionné.
                visible |= Q(is_active=True, is_deleted=False)
            queryset = Offer.objects.filter(visible)
        elif my_offers == 'true' and self.request.user.is_authenticated:
            queryset = Offer.objects.filter(seller=self.request.user, is_deleted=False)
        elif self.action == 'list':
            queryset = self.apply_filters(queryset)

        queryset = queryset.select_related('seller').prefetch_related('images')
        if ordering == '-visibility_score':
            # Pertinence : score stocké (E x R) x proximité D, appliquée dans le tri SQL.
            return services.order_by_relevance(queryset, self.get_near_commune())
        return queryset.order_by(ordering, '-created_at', 'id')

    def get_near_commune(self):
        """Commune de référence de la proximité D : paramètre `near` (un identifiant invalide est
        ignoré), sinon commune du profil de l'utilisateur connecté, sinon aucune."""
        near = parse_uuid(self.request.query_params.get('near'))
        if near is None and self.request.user.is_authenticated:
            near = self.request.user.commune_id
        return near

    def apply_filters(self, queryset):
        """Filtres dynamiques (CDC 3.2). Les référentiels vivent dans `catalog` : pas de
        jointure, on résout en UUID via son service. Un identifiant invalide ne renvoie aucune offre."""
        params = self.request.query_params

        search = params.get('search')
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(description__icontains=search))

        category = params.get('category')
        if category:
            category_uuid = parse_uuid(category)
            queryset = queryset.filter(category_id=category_uuid) if category_uuid else queryset.none()

        # Les filtres ville/lieu deviennent `commune_id IN (...)` : la liste est plafonnée
        # par catalog.services (MAX_COMMUNE_IDS) pour rester sous la limite de variables SQLite.
        location = params.get('location')
        if location:
            queryset = queryset.filter(commune_id__in=catalog_services.search_commune_ids(location))

        city = params.get('city')
        if city:
            queryset = queryset.filter(commune_id__in=catalog_services.get_commune_ids_for_city(city))

        commune = params.get('commune')
        if commune:
            commune_uuid = parse_uuid(commune)
            queryset = queryset.filter(commune_id=commune_uuid) if commune_uuid else queryset.none()

        if params.get('currency') in ('USD', 'CDF'):
            queryset = queryset.filter(currency=params['currency'])

        condition = params.get('condition')
        if condition:
            queryset = queryset.filter(condition=condition)

        is_exchangeable = params.get('is_exchangeable')
        if is_exchangeable is not None:
            queryset = queryset.filter(is_exchangeable=is_exchangeable.lower() == 'true')

        for param, lookup in (('price_min', 'price__gte'), ('price_max', 'price__lte')):
            if params.get(param):
                price = parse_price(params[param])
                queryset = queryset.filter(**{lookup: price}) if price is not None else queryset.none()

        seller = params.get('seller')
        if seller:
            seller_uuid = parse_uuid(seller)
            queryset = queryset.filter(seller_id=seller_uuid) if seller_uuid else queryset.none()
        return queryset

    def perform_create(self, serializer):
        # L'utilisateur connecté est automatiquement le vendeur
        serializer.save(seller=self.request.user)

    def perform_destroy(self, instance):
        record_audit(self.request.user, 'OFFER_DELETED', target=instance, details=instance.title)
        services.delete_offers(Offer.objects.filter(pk=instance.pk))

    @action(detail=False, methods=['post'])
    def recalculate_all_scores(self, request):
        """Force le recalcul des scores pour toutes les annonces actives."""
        count = services.refresh_all_scores()
        return Response({"message": f"Scores recalculés pour {count} annonces."})

    # 1. Corbeille de l'utilisateur connecté
    @action(detail=False, methods=['get'])
    def trash(self, request):
        trashed = (
            Offer.objects.filter(seller=request.user, is_deleted=True)
            .select_related('seller').prefetch_related('images').order_by('-created_at')
        )
        page = self.paginate_queryset(trashed)
        serializer = self.get_serializer(page if page is not None else trashed, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    # 2. « Supprimer » (envoyer à la corbeille) sans supprimer de la base
    @action(detail=True, methods=['post'])
    def soft_delete(self, request, pk=None):
        services.move_to_trash(self.get_object())
        return Response({"message": "Annonce déplacée dans la corbeille"})

    # 3. Restaurer une annonce
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        services.restore_from_trash(self.get_object())
        return Response({"message": "Annonce restaurée"})

    # 4. Supprimer définitivement une annonce
    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        offer = self.get_object()
        record_audit(request.user, 'OFFER_DELETED', target=offer, details=offer.title)
        services.delete_offers(Offer.objects.filter(pk=offer.pk))
        return Response({"message": "Annonce supprimée définitivement"})

    # Cycle de vie (CDC 3.2, 3.9) : pause, reprise, vente, renouvellement.
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        offer = self.get_object()
        services.pause_offer(offer)
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=['post'])
    def unpause(self, request, pk=None):
        offer = self.get_object()
        try:
            resumed = services.unpause_offer(offer)
        except services.OfferHiddenError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        if not resumed:
            return Response(
                {"error": "Cette annonce a expiré. Renouvelez-la plutôt.", "status": offer.status},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=['post'])
    def mark_sold(self, request, pk=None):
        offer = self.get_object()
        services.mark_offer_sold(offer)
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        offer = self.get_object()
        try:
            services.renew_offer(offer)
        except services.OfferHiddenError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(offer).data)

    # 5. Galerie de photos (CDC 3.2 : 1 à 8 photos par annonce, main_image comprise)
    @action(detail=True, methods=['post'])
    def images(self, request, pk=None):
        offer = self.get_object()

        current_count = offer.images.count() + 1  # + main_image
        uploaded = request.FILES.getlist('image')
        if not uploaded:
            return Response({"error": "Aucune image fournie."}, status=status.HTTP_400_BAD_REQUEST)
        if current_count + len(uploaded) > OfferImage.MAX_IMAGES_PER_OFFER:
            return Response(
                {"error": f"Une annonce ne peut pas dépasser {OfferImage.MAX_IMAGES_PER_OFFER} photos."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Fichiers contrôlés avant tout enregistrement : un fichier invalide donne un 400, pas un 500.
        for image in uploaded:
            try:
                validate_image_upload_size(image)
                validate_image_pixels(image)
            except DjangoValidationError as exc:
                return Response({"error": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        created = [OfferImage.objects.create(offer=offer, image=f) for f in uploaded]
        return Response(OfferImageSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @images.mapping.delete
    def delete_image(self, request, pk=None):
        offer = self.get_object()
        image_uuid = parse_uuid(request.query_params.get('image_id'))
        deleted = 0
        if image_uuid:
            deleted, _ = offer.images.filter(pk=image_uuid).delete()
        if not deleted:
            return Response({"error": "Photo introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # 6. Partage externe (CDC 3.4) : simple compteur, alimente l'engagement (CDC 3.8).
    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        return Response({"shares_count": services.register_share(self.get_object(), request.user)})

    # 7. Favoris (CDC 3.2)
    @action(detail=True, methods=['post'])
    def favorite(self, request, pk=None):
        return Response({"favorited": services.toggle_favorite(request.user, self.get_object())})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # CDC 3.8 : une vue unique par jour et par visiteur. Un visiteur anonyme n'est compté que
        # si son cookie a été émis ET signé par le serveur (pas de fabrication d'empreintes).
        # Le vendeur qui consulte sa propre offre ne gonfle pas ses statistiques.
        anon_id = None if request.user.is_authenticated else read_anon_id(request)
        is_owner = request.user.is_authenticated and instance.seller_id == request.user.id
        if (request.user.is_authenticated or anon_id) and not is_owner:
            services.register_view(instance, visibility_services.build_viewer_key(request.user, anon_id))

        response = Response(self.get_serializer(instance).data)
        if not request.user.is_authenticated and anon_id is None:
            response.set_cookie(
                ANON_COOKIE, signing.dumps(uuid.uuid4().hex, salt=ANON_COOKIE_SALT),
                max_age=settings.ANON_VIEW_COOKIE_MAX_AGE,
                httponly=True,
                samesite='Lax',
                secure=not settings.DEBUG,
            )
        return response


class FavoriteViewSet(ActionScopedThrottleMixin, viewsets.ModelViewSet):
    """Liste personnelle des favoris de l'utilisateur connecté (CDC 3.2)."""

    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    throttle_scopes = {'create': 'favorite'}

    def get_queryset(self):
        queryset = (
            Favorite.objects.filter(user=self.request.user)
            .select_related('offer', 'offer__seller').prefetch_related('offer__images')
        )
        if self.action == 'list':
            # Les offres masquées, en pause, vendues ou en corbeille ne sont plus montrées.
            queryset = queryset.filter(
                offer__is_active=True, offer__is_deleted=False, offer__seller__is_active=True,
            )
        return queryset

    def perform_create(self, serializer):
        try:
            serializer.instance, _ = services.add_favorite(self.request.user, serializer.validated_data['offer'])
        except services.MarketplaceError as exc:
            raise ValidationError({'post_id': str(exc)})

    def perform_destroy(self, instance):
        services.remove_favorite(instance)


class _OfferMessageViewSet(ActionScopedThrottleMixin, viewsets.ModelViewSet):
    """Base des contacts et propositions d'échange : l'utilisateur ne voit que les siens ;
    ni modification ni suppression (traçabilité)."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'head', 'options']
    model = None

    def get_queryset(self):
        return self.model.objects.filter(sender=self.request.user).select_related('sender').order_by('-created_at')

    def perform_create(self, serializer):
        offer = serializer.validated_data['offer']
        try:
            serializer.instance = self.create_with_service(offer, serializer.validated_data['message'])
        except services.MarketplaceError as exc:
            raise ValidationError({'post': str(exc)})


class ContactEventViewSet(_OfferMessageViewSet):
    throttle_scopes = {'create': 'contact'}
    serializer_class = ContactEventSerializer
    model = ContactEvent

    def create_with_service(self, offer, message):
        return services.create_contact_event(offer=offer, sender=self.request.user, message=message)


class ExchangeProposalViewSet(_OfferMessageViewSet):
    throttle_scopes = {'create': 'exchange'}
    serializer_class = ExchangeProposalSerializer
    model = ExchangeProposal

    def create_with_service(self, offer, message):
        return services.create_exchange_proposal(offer=offer, sender=self.request.user, message=message)
