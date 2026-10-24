from rest_framework import serializers

from apps.common.serializers import PreloadingListSerializer
from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.moderation import services as moderation_services

from . import services
from .models import CONTENT_MAX_LENGTH, CONTENT_MIN_LENGTH, Review

SOURCE_CONTACT = 'CONTACT'  # libellé front : « Avis après contact »

CONTENT_MESSAGES = {
    'blank': f"L'avis doit contenir entre {CONTENT_MIN_LENGTH} et {CONTENT_MAX_LENGTH} caractères.",
    'required': "Le commentaire est requis.",
    'null': "Le commentaire est requis.",
    'min_length': f"L'avis doit contenir au moins {CONTENT_MIN_LENGTH} caractères.",
    'max_length': f"L'avis ne doit pas dépasser {CONTENT_MAX_LENGTH} caractères.",
}
RATING_MESSAGES = {
    'required': "La note est requise.",
    'null': "La note est requise.",
    'invalid': "La note doit être un nombre entier de 1 à 5.",
    'min_value': "La note doit être comprise entre 1 et 5.",
    'max_value': "La note doit être comprise entre 1 et 5.",
}


class OfferLookupMixin:
    """Charge par lot les offres citées (domaine marketplace) : existence et titre. Une offre
    purgée n'est plus trouvée : la clé JSON `post` vaut alors null."""

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
    """Lecture d'un avis (contrat de l'ADR 0004, 7.2). Le canal du contact et la date du contact
    ne sont pas exposés publiquement (modération seulement)."""

    post = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    is_post_owner = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    contest_report_id = serializers.SerializerMethodField()
    contest_responded = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id', 'post', 'user_name', 'offer_rating', 'seller_rating', 'content', 'source',
            'reply_content', 'reply_at', 'created_at', 'edited_at', 'is_post_owner', 'is_mine', 'can_edit',
            'can_delete', 'contest_report_id', 'contest_responded',
        ]
        read_only_fields = fields
        list_serializer_class = ReviewListSerializer

    STATES_KEY = 'reviews_open_report_states'
    REPLY_CONTEXTS_KEY = 'reviews_reply_contexts'

    @classmethod
    def preload(cls, items, context):
        super().preload(items, context)
        # Signalements ouverts : lus en une requête, pour les seuls avis de l'appelant.
        request = context.get('request')
        cache = context.setdefault(cls.STATES_KEY, {})
        if request and request.user.is_authenticated:
            wanted = {i.id for i in items if i.user_id == request.user.id} - cache.keys()
            if wanted:
                found = moderation_services.get_open_report_states('review', wanted)
                for review_id in wanted:
                    cache[review_id] = found.get(review_id, {})

    def _state(self, obj):
        """État des signalements ouverts d'un avis de l'appelant (jamais celui d'un autre auteur)."""
        if not self.get_is_mine(obj):
            return {}
        if obj.id not in self.context.get(self.STATES_KEY, {}):
            self.preload([obj], self.context)
        return self.context[self.STATES_KEY].get(obj.id, {})

    def get_user_name(self, obj):
        return identity_services.public_display_name(obj.user.full_name)

    def get_source(self, obj):
        return SOURCE_CONTACT

    def get_is_post_owner(self, obj):
        """Le demandeur peut répondre à cet avis (capacité `review.reply` du contexte vendeur de l'avis). Les
        contextes de réponse du demandeur sont calculés UNE fois par sérialisation (4 requêtes au plus), pas par
        avis : le coût ne dépend pas du nombre d'avis de la page."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        if self.REPLY_CONTEXTS_KEY not in self.context:
            self.context[self.REPLY_CONTEXTS_KEY] = services.get_reply_contexts(request.user)
        return (obj.seller_context_type, obj.seller_context_id) in self.context[self.REPLY_CONTEXTS_KEY]

    def get_is_mine(self, obj):
        # L'identifiant de l'auteur n'est jamais public : seul l'auteur apprend que l'avis est le sien.
        request = self.context.get('request')
        return bool(request and request.user.is_authenticated and obj.user_id == request.user.id)

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not self.get_is_mine(obj) or obj.is_hidden or obj.reply_content:
            return False
        # Une lecture par sérialisation de liste : le contexte est partagé.
        if 'review_edit_window_hours' not in self.context:
            self.context['review_edit_window_hours'] = services.get_settings().edit_window_hours
        return obj.can_still_be_edited(self.context['review_edit_window_hours'])

    def get_can_delete(self, obj):
        # Miroir de `ensure_author_can_modify(deleting=True)` et de la règle « réponse reçue ».
        if not self.get_is_mine(obj) or obj.is_hidden or obj.reply_content:
            return False
        return not self._state(obj).get('grave', False)

    def get_contest_report_id(self, obj):
        report_id = self._state(obj).get('contest_report_id')
        return str(report_id) if report_id else None

    def get_contest_responded(self, obj):
        return bool(self._state(obj).get('contest_responded', False))


class ReviewCreateSerializer(serializers.Serializer):
    """Corps de `POST /reviews/` : une clé inconnue (par exemple une ancienne clé d'affaire) est ignorée."""

    post = serializers.UUIDField(
        error_messages={'required': "L'annonce est requise.", 'null': "L'annonce est requise.",
                        'invalid': "Identifiant d'annonce invalide."},
    )
    offer_rating = serializers.IntegerField(min_value=1, max_value=5, error_messages=RATING_MESSAGES)
    seller_rating = serializers.IntegerField(min_value=1, max_value=5, error_messages=RATING_MESSAGES)
    content = serializers.CharField(
        min_length=CONTENT_MIN_LENGTH, max_length=CONTENT_MAX_LENGTH, error_messages=CONTENT_MESSAGES,
    )


class ReviewUpdateSerializer(serializers.Serializer):
    """Corps de `PATCH /reviews/{id}/` : sous-ensemble de notes et de commentaire ; `post` est ignoré.
    Les trois champs sont déclarés requis, mais la vue instancie le serializer avec `partial=True` :
    chacun est facultatif, et au moins un doit être fourni (`validate`)."""

    offer_rating = serializers.IntegerField(min_value=1, max_value=5, error_messages=RATING_MESSAGES)
    seller_rating = serializers.IntegerField(min_value=1, max_value=5, error_messages=RATING_MESSAGES)
    content = serializers.CharField(
        min_length=CONTENT_MIN_LENGTH, max_length=CONTENT_MAX_LENGTH, error_messages=CONTENT_MESSAGES,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Aucune modification fournie.")
        return attrs


class ReviewReplySerializer(serializers.Serializer):
    reply_content = serializers.CharField(
        max_length=CONTENT_MAX_LENGTH,
        error_messages={
            'required': "Le contenu de la réponse est requis.", 'blank': "Le contenu de la réponse est requis.",
            'null': "Le contenu de la réponse est requis.",
            'max_length': f"La réponse ne doit pas dépasser {CONTENT_MAX_LENGTH} caractères.",
        },
    )
