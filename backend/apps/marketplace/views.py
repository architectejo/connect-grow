import uuid
from collections import defaultdict
from urllib.parse import quote
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.response import Response

from apps.catalog import services as catalog_services
from apps.common.images import validate_image_pixels, validate_image_upload_size
from apps.common.exception_handler import CodedAPIException, throttled_message
from apps.common.pagination import OptionalPagination, StandardPagination
from apps.common.throttles import (
    ActionScopedThrottleMixin, AnonymousOrUserScopedThrottle, AnonymousScopedThrottle, RevealIpThrottle,
    RevealUserThrottle,
)
from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
from apps.identity import services as identity_services
from apps.identity.services import capability_permission
from apps.moderation.permissions import can_moderate
from apps.common.utils import parse_uuid
from apps.visibility import services as visibility_services

from . import services
from .models import ContactEvent, ExchangeProposal, Favorite, Offer, OfferImage
from .permissions import HasOfferCapability
from .serializers import (
    ContactEventSerializer, ExchangeProposalSerializer, FavoriteSerializer, OfferImageSerializer,
    OfferSerializer, ReceivedRevealSerializer, RevealRequestSerializer, RevealResponseSerializer,
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


# Champs que le corps d'une requête ne peut jamais imposer : le vendeur est posé par le serveur d'après le
# contexte actif (ADR 0006, 9.6).
SERVER_OWNED_FIELDS = ('seller', 'seller_context_type', 'seller_context_id', 'created_by', 'seller_is_public')


def reject_server_owned_fields(request):
    """400 `seller_not_settable` si le corps tente de désigner le vendeur ou l'auteur de l'offre."""
    if any(field in request.data for field in SERVER_OWNED_FIELDS):
        raise ValidationError({'seller_context_id': [ErrorDetail(
            "Le vendeur de l'annonce est déterminé par le serveur : il ne peut pas être envoyé.",
            code='seller_not_settable',
        )]})


class OfferViewSet(identity_services.ActingContextMixin, ActionScopedThrottleMixin, viewsets.ModelViewSet):
    """Offres de la marketplace.

    Contexte vendeur (ADR 0006, 6.4) : la CRÉATION et les listes « de mon contexte » (`my_posts`, `trash`)
    lisent l'en-tête `X-Context` ; toute action sur une offre EXISTANTE est autorisée d'après son contexte
    propriétaire (`HasOfferCapability`), jamais d'après l'en-tête. `share` et `favorite` sont des gestes
    d'acheteur (toujours personnels, Q-CP8) et `recalculate_all_scores` une action du personnel."""

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
            return [permissions.IsAuthenticated(), HasOfferCapability()]
        if self.action == 'create':
            return [permissions.IsAuthenticated(), capability_permission(services.CAP_PUBLISH)()]
        if self.action == 'recalculate_all_scores':
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        if self.action in self.OWNER_ACTIONS:
            # Pas de filtre par vendeur : l'autorisation se fait par objet (`HasOfferCapability`), d'après le
            # contexte propriétaire et le rôle réel ; un tiers reçoit 403 `DENY_RELATION`.
            return Offer.objects.all().prefetch_related('images')

        # On trie par le score de visibilité organique (E x R, ADR 0004) par défaut
        ordering = self.request.query_params.get('ordering', '-visibility_score')
        if ordering not in self.ORDERINGS:
            ordering = '-visibility_score'

        # Par défaut (Marketplace), on ne montre que ce qui n'est pas supprimé et actif
        # Les offres d'un vendeur non public (compte suspendu ou banni, profil archivé, organisation suspendue
        # ou archivée) ne sont plus publiques : `seller_is_public`, dénormalisé depuis `identity`.
        queryset = services.public_offers()

        # Filtre pour récupérer les offres de l'utilisateur connecté
        my_offers = self.request.query_params.get('my_posts')
        if self.action == 'retrieve' and self.request.user.is_authenticated:
            # Le vendeur retrouve toutes ses offres (pause, vendue, expirée, masquée par la
            # modération, corbeille) ; le public et les tiers restent limités aux offres actives.
            # Même requête SQL : seule la clause WHERE change.
            visible = Q(is_active=True, is_deleted=False, seller_is_public=True) | self._own_contexts_filter()
            if can_moderate(self.request.user):
                # La modération consulte aussi les offres d'un vendeur sanctionné.
                visible |= Q(is_active=True, is_deleted=False)
            queryset = Offer.objects.filter(visible)
        elif my_offers == 'true' and self.request.user.is_authenticated:
            # « Mes annonces » : uniquement celles du CONTEXTE ACTIF (en-tête `X-Context`, ADR 0006, 6.4).
            ctx = self.authorize_capability(services.CAP_VIEW_INTERNAL)
            queryset = Offer.objects.filter(seller_context_type=ctx.type, seller_context_id=ctx.id, is_deleted=False)
        elif self.action == 'list':
            queryset = self.apply_filters(queryset)

        queryset = queryset.prefetch_related('images')
        if ordering == '-visibility_score':
            # Pertinence : score stocké (E x R) x proximité D, appliquée dans le tri SQL.
            return services.order_by_relevance(queryset, self.get_near_commune())
        return queryset.order_by(ordering, '-created_at', 'id')

    def _own_contexts_filter(self):
        """Filtre « offres des contextes dans lesquels l'utilisateur peut agir » (personnel, prestataire actif,
        organisations actives dont il est membre) : deux requêtes, aucun cache."""
        by_type = defaultdict(list)
        for context_type, context_id in identity_services.get_user_context_roles(self.request.user.pk):
            by_type[context_type].append(context_id)
        condition = Q()
        for context_type, ids in by_type.items():
            condition |= Q(seller_context_type=context_type, seller_context_id__in=ids)
        return condition

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
        # Troc désactivé : le filtre est ignoré (comme tout paramètre inconnu).
        if is_exchangeable is not None and services.is_exchange_enabled():
            queryset = queryset.filter(is_exchangeable=is_exchangeable.lower() == 'true')

        for param, lookup in (('price_min', 'price__gte'), ('price_max', 'price__lte')):
            if params.get(param):
                price = parse_price(params[param])
                queryset = queryset.filter(**{lookup: price}) if price is not None else queryset.none()

        # `seller` désigne un IDENTIFIANT DE CONTEXTE vendeur (plus un compte) ; `seller_type` le précise
        # (USER, PROVIDER, ORGANIZATION). Sans lui, n'importe quel type ; inconnu : liste vide.
        seller = params.get('seller')
        if seller:
            seller_uuid = parse_uuid(seller)
            seller_type = params.get('seller_type')
            if seller_uuid is None or (
                seller_type and seller_type not in (CONTEXT_USER, CONTEXT_PROVIDER, CONTEXT_ORGANIZATION)
            ):
                return queryset.none()
            queryset = queryset.filter(seller_context_id=seller_uuid)
            if seller_type:
                queryset = queryset.filter(seller_context_type=seller_type)
        return queryset

    def create(self, request, *args, **kwargs):
        reject_server_owned_fields(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        reject_server_owned_fields(request)
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Le vendeur est le contexte actif (en-tête `X-Context`, absent = personnel), jamais le corps.
        ctx = self.acting_context
        serializer.instance = services.create_offer(
            actor=self.request.user, context_type=ctx.type, context_id=ctx.id, data=dict(serializer.validated_data),
        )

    def perform_update(self, serializer):
        serializer.instance = services.update_offer(
            serializer.instance, actor=self.request.user, changes=serializer.validated_data,
        )

    def perform_destroy(self, instance):
        services.delete_offer(instance, actor=self.request.user)

    @action(detail=False, methods=['post'])
    def recalculate_all_scores(self, request):
        """Force le recalcul des scores pour toutes les annonces actives."""
        count = services.refresh_all_scores()
        return Response({"message": f"Scores recalculés pour {count} annonces."})

    # 1. Corbeille de l'utilisateur connecté
    @action(detail=False, methods=['get'])
    def trash(self, request):
        # Corbeille du CONTEXTE ACTIF (en-tête `X-Context`), capacité `offer.view_internal`.
        ctx = self.authorize_capability(services.CAP_VIEW_INTERNAL)
        trashed = (
            Offer.objects.filter(seller_context_type=ctx.type, seller_context_id=ctx.id, is_deleted=True)
            .prefetch_related('images').order_by('-created_at')
        )
        page = self.paginate_queryset(trashed)
        serializer = self.get_serializer(page if page is not None else trashed, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    # 2. « Supprimer » (envoyer à la corbeille) sans supprimer de la base
    @action(detail=True, methods=['post'])
    def soft_delete(self, request, pk=None):
        services.move_to_trash(self.get_object(), actor=request.user)
        return Response({"message": "Annonce déplacée dans la corbeille"})

    # 3. Restaurer une annonce
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        services.restore_from_trash(self.get_object(), actor=request.user)
        return Response({"message": "Annonce restaurée"})

    # 4. Supprimer définitivement une annonce
    @action(detail=True, methods=['delete'])
    def hard_delete(self, request, pk=None):
        services.delete_offer(self.get_object(), actor=request.user)
        return Response({"message": "Annonce supprimée définitivement"})

    # Cycle de vie (CDC 3.2, 3.9) : pause, reprise, vente, renouvellement.
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        offer = self.get_object()
        services.pause_offer(offer, actor=request.user)
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=['post'])
    def unpause(self, request, pk=None):
        offer = self.get_object()
        try:
            resumed = services.unpause_offer(offer, actor=request.user)
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
        services.mark_offer_sold(offer, actor=request.user)
        return Response(self.get_serializer(offer).data)

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        offer = self.get_object()
        try:
            services.renew_offer(offer, actor=request.user)
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
        # Un membre qui consulte l'offre de son contexte ne gonfle pas les statistiques de ce contexte.
        is_owner = request.user.is_authenticated and (
            (instance.seller_context_type, instance.seller_context_id)
            in identity_services.get_user_context_roles(request.user.pk)
        )
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

    acting_context_exempt = "favoris : geste d'acheteur, toujours personnel (ADR 0006, Q-CP8)"

    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'delete', 'head', 'options']
    throttle_scopes = {'create': 'favorite'}

    def get_queryset(self):
        queryset = (
            Favorite.objects.filter(user=self.request.user)
            .select_related('offer').prefetch_related('offer__images')
        )
        if self.action == 'list':
            # Les offres masquées, en pause, vendues ou en corbeille ne sont plus montrées.
            queryset = queryset.filter(
                offer__is_active=True, offer__is_deleted=False, offer__seller_is_public=True,
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
            if exc.code:
                raise CodedAPIException(exc.message, exc.code, exc.status_code, wait=exc.wait)
            raise ValidationError({'post': str(exc)})


class ContactEventViewSet(identity_services.ActingContextMixin, _OfferMessageViewSet):
    """Contacts. Écrire au vendeur et obtenir son numéro sont des gestes d'acheteur, toujours personnels
    (Q-CP8, en-tête ignoré). Seule « qui a demandé mon numéro » (`reveals/received/`) est sensible au
    contexte : en-tête `X-Context` et capacité `contact.view_requesters` (l'analyste est refusé)."""

    throttle_scopes = {'create': 'contact', 'reveals_received': 'contact_reveals_list'}
    serializer_class = ContactEventSerializer
    model = ContactEvent

    def create_with_service(self, offer, message):
        return services.create_contact_event(offer=offer, sender=self.request.user, message=message)

    # --- Révélation du numéro de contact (ADR 0005, 5.4 et 5.5) ---

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == 'reveal':
            throttles += [RevealIpThrottle(), RevealUserThrottle()]
        return throttles

    def check_throttles(self, request):
        """Pour la révélation, un dépassement répond 429 avec le code de la limite atteinte
        (`reveal_quota_ip`) et `Retry-After`."""
        if self.action != 'reveal':
            return super().check_throttles(request)
        for throttle in self.get_throttles():
            if not throttle.allow_request(request, self):
                wait = throttle.wait()
                raise CodedAPIException(
                    throttled_message(wait) + " " + services.REVEAL_FALLBACK,
                    getattr(throttle, 'code', 'throttled'), status.HTTP_429_TOO_MANY_REQUESTS,
                    wait=None if wait is None else max(1, int(wait)),
                )

    @staticmethod
    def _no_store(response):
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        return response

    @action(detail=False, methods=['post'], url_path='reveal')
    def reveal(self, request):
        body = RevealRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = services.reveal_contact(
                offer_id=body.validated_data['offer'], sender=request.user, channel=body.validated_data['channel'],
            )
        except services.RevealError as exc:
            raise CodedAPIException(exc.message, exc.code, exc.status_code, wait=exc.wait)
        digits = result.phone.lstrip('+')
        is_call = result.channel == ContactEvent.CHANNEL_CALL
        data = {
            'contact_event_id': result.contact_event_id, 'channel': result.channel, 'created': result.created,
            'phone': result.phone,
            'tel_url': f"tel:{result.phone}" if is_call else None,
            # Le texte prérempli ne contient que le titre public de l'offre.
            'whatsapp_url': None if is_call else f"https://wa.me/{digits}?text={quote(result.offer_title, safe='')}",
        }
        response = Response(RevealResponseSerializer(data).data, status=201 if result.created else 200)
        return self._no_store(response)

    @action(detail=False, methods=['get'], url_path='reveals/received')
    def reveals_received(self, request):
        channel = request.query_params.get('channel')
        if channel and channel not in services.REVEAL_CHANNELS:
            raise CodedAPIException("Moyen de contact invalide.", 'channel_invalid', status.HTTP_400_BAD_REQUEST)
        ctx = self.authorize_capability('contact.view_requesters')
        paginator = StandardPagination()
        page = paginator.paginate_queryset(
            services.list_reveals_for_seller(ctx.type, ctx.id, channel), request, view=self,
        )
        rows = services.to_received_reveals(page)
        response = paginator.get_paginated_response(ReceivedRevealSerializer(rows, many=True).data)
        return self._no_store(response)


class ExchangeProposalViewSet(_OfferMessageViewSet):
    acting_context_exempt = "troc : geste d'acheteur, toujours personnel (ADR 0006, Q-CP8)"
    throttle_scopes = {'create': 'exchange'}
    serializer_class = ExchangeProposalSerializer
    model = ExchangeProposal

    def check_permissions(self, request):
        """Troc désactivé : 403 `feature_disabled` pour tout appel authentifié, avant validation,
        limitation de débit et création (aucun effet de bord)."""
        super().check_permissions(request)
        if not services.is_exchange_enabled():
            raise CodedAPIException(
                services.FEATURE_DISABLED_MESSAGE, 'feature_disabled', status.HTTP_403_FORBIDDEN,
            )

    def create_with_service(self, offer, message):
        return services.create_exchange_proposal(offer=offer, sender=self.request.user, message=message)
