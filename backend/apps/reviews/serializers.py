from rest_framework import serializers

from apps.common.serializers import PreloadingListSerializer
from apps.marketplace import services as marketplace_services

from . import services
from .models import Deal, Review


class OfferLookupMixin:
    """Charge par lot les offres citées (domaine marketplace) : titre, vendeur, existence.
    Une offre purgée n'est plus trouvée : la clé JSON `post` vaut alors null."""

    OFFERS_KEY = 'reviews_offers'

    @classmethod
    def preload(cls, items, context):
        cache = context.setdefault(cls.OFFERS_KEY, {})
        missing = {i.offer_id for i in items if i.offer_id} - cache.keys()
        cache.update(marketplace_services.get_offers_by_ids(missing))
        for offer_id in missing:
            cache.setdefault(offer_id, None)

    def _offer(self, obj):
        if not obj.offer_id:
            return None
        cache = self.context.get(self.OFFERS_KEY)
        if cache is None or obj.offer_id not in cache:
            self.preload([obj], self.context)
            cache = self.context[self.OFFERS_KEY]
        return cache[obj.offer_id]

    def get_post(self, obj):
        return str(obj.offer_id) if self._offer(obj) else None


class ReviewListSerializer(PreloadingListSerializer):
    pass


class ReviewSerializer(OfferLookupMixin, serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.full_name')
    user_id = serializers.ReadOnlyField()
    reviewed_user_id = serializers.ReadOnlyField()
    is_post_owner = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    # `post` est dérivé de l'affaire côté serveur (voir validate) pour éviter toute
    # incohérence entre l'offre fournie par le client et celle de l'affaire.
    post = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id', 'post', 'deal', 'user_id', 'user_name', 'reviewed_user_id', 'content', 'rating',
            'reply_content', 'reply_at', 'created_at', 'is_post_owner', 'can_edit',
        ]
        # La réponse ne s'écrit que par l'action `reply` (personne évaluée), jamais par l'auteur.
        read_only_fields = ['user', 'reply_content', 'reply_at']
        list_serializer_class = ReviewListSerializer

    def get_is_post_owner(self, obj):
        request = self.context.get('request')
        offer = self._offer(obj)
        if request and request.user and offer:
            return offer.seller_id == request.user.id
        return False

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not request or obj.user_id != getattr(request.user, 'id', None):
            return False
        return obj.can_still_be_edited()

    def validate(self, data):
        user = self.context['request'].user

        if not self.instance:
            try:
                reviewed_user = services.validate_new_review(user, data.get('deal'))
            except services.ReviewError as exc:
                raise serializers.ValidationError({exc.field: exc.message} if exc.field else exc.message)
            data['offer_id'] = data['deal'].offer_id
            data['reviewed_user'] = reviewed_user
        else:
            if not self.instance.can_still_be_edited():
                raise serializers.ValidationError("L'avis n'est plus modifiable après 48 heures.")
            # L'affaire et la personne évaluée ne changent jamais après coup.
            data.pop('deal', None)

        return data


class DealListSerializer(PreloadingListSerializer):
    pass


class DealSerializer(OfferLookupMixin, serializers.ModelSerializer):
    initiator_name = serializers.ReadOnlyField(source='initiator.full_name')
    counterparty_name = serializers.ReadOnlyField(source='counterparty.full_name')
    # Clés JSON `post` / `post_title` conservées jusqu'à L0-11 : UUID de l'offre.
    post = serializers.UUIDField(source='offer_id')
    post_title = serializers.SerializerMethodField()

    class Meta:
        model = Deal
        fields = [
            'id', 'post', 'post_title', 'initiator', 'initiator_name',
            'counterparty', 'counterparty_name', 'status', 'created_at', 'confirmed_at',
        ]
        read_only_fields = ['initiator', 'status', 'created_at', 'confirmed_at']
        list_serializer_class = DealListSerializer

    def get_post_title(self, obj):
        offer = self._offer(obj)
        return offer.title if offer else None

    def validate_post(self, value):
        offer = marketplace_services.get_offer(value)
        if offer is None:
            raise serializers.ValidationError("Annonce introuvable.")
        if not offer.is_available:
            raise serializers.ValidationError("Cette annonce n'est plus disponible.")
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        offer = marketplace_services.get_offer(attrs['offer_id'])
        counterparty = attrs['counterparty']

        if counterparty.id == user.id:
            raise serializers.ValidationError("Vous ne pouvez pas déclarer une affaire avec vous-même.")

        # CDC 3.7 : au MVP, la déclaration se fait depuis l'historique des contacts.
        contacted_user_ids = marketplace_services.get_contact_sender_ids(offer.id)

        if offer.seller_id == user.id:
            if counterparty.id not in contacted_user_ids:
                raise serializers.ValidationError("La contrepartie doit avoir contacté cette annonce.")
        else:
            if user.id not in contacted_user_ids:
                raise serializers.ValidationError(
                    "Vous devez avoir contacté cette annonce avant de déclarer une affaire."
                )
            if counterparty.id != offer.seller_id:
                raise serializers.ValidationError("La contrepartie doit être le vendeur de l'annonce.")

        return attrs
