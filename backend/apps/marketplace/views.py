import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.catalog import services as catalog_services
from apps.common.images import validate_image_pixels, validate_image_upload_size
from apps.common.pagination import OptionalPagination
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


class OfferViewSet(viewsets.ModelViewSet):
    serializer_class = OfferSerializer
    pagination_class = OptionalPagination

    # Actions réservées au vendeur : elles portent aussi sur des offres inactives (pause,
    # expirée, corbeille), donc hors du queryset public.
    OWNER_ACTIONS = {
        'update', 'partial_update', 'destroy', 'soft_delete', 'restore', 'hard_delete',
        'pause', 'unpause', 'mark_sold', 'renew', 'images', 'delete_image',
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
            return Offer.objects.select_related('seller').prefetch_related('images')

        # On trie par le score de visibilité "Trust & Engage" par défaut
        ordering = self.request.query_params.get('ordering', '-visibility_score')
        if ordering not in self.ORDERINGS:
            ordering = '-visibility_score'

        # Par défaut (Marketplace), on ne montre que ce qui n'est pas supprimé et actif
        queryset = Offer.objects.filter(is_active=True, is_deleted=False)

        # Filtre pour récupérer les offres de l'utilisateur connecté
        my_offers = self.request.query_params.get('my_posts')
        if my_offers == 'true' and self.request.user.is_authenticated:
            queryset = Offer.objects.filter(seller=self.request.user, is_deleted=False)
        elif self.action == 'list':
            queryset = self.apply_filters(queryset)

        return queryset.select_related('seller').prefetch_related('images').order_by(ordering, '-created_at')

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
        services.delete_offers(Offer.objects.filter(pk=self.get_object().pk))
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
        if not services.unpause_offer(offer):
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
        services.renew_offer(offer)
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
        return Response({"shares_count": services.register_share(self.get_object())})

    # 7. Favoris (CDC 3.2)
    @action(detail=True, methods=['post'])
    def favorite(self, request, pk=None):
        return Response({"favorited": services.toggle_favorite(request.user, self.get_object())})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # CDC 3.8 : une vue unique par jour et par utilisateur (ou empreinte anonyme),
        # garantie par une contrainte d'unicité en base plutôt qu'un simple cookie.
        anon_id = request.COOKIES.get('anon_id') or uuid.uuid4().hex
        services.register_view(instance, visibility_services.build_viewer_key(request.user, anon_id))

        response = Response(self.get_serializer(instance).data)
        if not request.COOKIES.get('anon_id'):
            response.set_cookie(
                'anon_id', anon_id,
                max_age=365 * 86400,
                httponly=True,
                samesite='Lax',
                secure=not settings.DEBUG,
            )
        return response


class FavoriteViewSet(viewsets.ModelViewSet):
    """Liste personnelle des favoris de l'utilisateur connecté (CDC 3.2)."""

    serializer_class = FavoriteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        return (
            Favorite.objects.filter(user=self.request.user)
            .select_related('offer', 'offer__seller').prefetch_related('offer__images')
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class _OfferMessageViewSet(viewsets.ModelViewSet):
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
    serializer_class = ContactEventSerializer
    model = ContactEvent

    def create_with_service(self, offer, message):
        return services.create_contact_event(offer=offer, sender=self.request.user, message=message)


class ExchangeProposalViewSet(_OfferMessageViewSet):
    serializer_class = ExchangeProposalSerializer
    model = ExchangeProposal

    def create_with_service(self, offer, message):
        return services.create_exchange_proposal(offer=offer, sender=self.request.user, message=message)
