from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.marketplace import services as marketplace_services

from .models import Report, Sanction

# Cache l'implémentation ContentType derrière des identifiants stables côté API.
TARGET_TYPE_MAP = {
    'POST': ('marketplace', 'offer'),
    'REVIEW': ('reviews', 'review'),
    'MESSAGE': ('messaging', 'message'),
    'USER': ('identity', 'user'),
}
TARGET_TYPE_REVERSE = {v: k for k, v in TARGET_TYPE_MAP.items()}


class ReportSerializer(serializers.ModelSerializer):
    target_type = serializers.ChoiceField(choices=list(TARGET_TYPE_MAP.keys()), write_only=True)
    target_type_display = serializers.SerializerMethodField()
    target_display = serializers.SerializerMethodField()
    reporter_name = serializers.ReadOnlyField(source='reporter.full_name')
    assigned_to_name = serializers.ReadOnlyField(source='assigned_to.full_name')

    class Meta:
        model = Report
        fields = [
            'id', 'target_type', 'target_type_display', 'object_id', 'target_display',
            'reporter_name', 'reason', 'description', 'status', 'assigned_to_name',
            'decision_notes', 'created_at', 'resolved_at',
        ]
        read_only_fields = ['status', 'decision_notes', 'created_at', 'resolved_at']

    def get_target_type_display(self, obj):
        return TARGET_TYPE_REVERSE.get((obj.content_type.app_label, obj.content_type.model))

    def get_target_display(self, obj):
        return str(obj.target) if obj.target else None

    def validate(self, attrs):
        target_type = attrs.pop('target_type')
        app_label, model_name = TARGET_TYPE_MAP[target_type]
        content_type = ContentType.objects.get(app_label=app_label, model=model_name)
        model_class = content_type.model_class()
        try:
            target = model_class.objects.filter(pk=attrs['object_id']).first()
        except (ValueError, TypeError, DjangoValidationError):
            target = None  # identifiant mal formé pour ce type de cible
        if target is None:
            raise serializers.ValidationError({'object_id': "Cible introuvable."})
        # Forme canonique de la clé (UUID en minuscules avec tirets) : un même objet
        # signalé sous plusieurs écritures reste regroupé.
        attrs['object_id'] = str(target.pk)
        attrs['content_type'] = content_type
        return attrs


class SanctionSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.full_name')
    # Clé JSON `related_post` conservée jusqu'à L0-11 : UUID de l'offre masquée.
    related_post = serializers.UUIDField(source='related_offer_id', required=False, allow_null=True)
    issued_by_name = serializers.ReadOnlyField(source='issued_by.full_name')

    class Meta:
        model = Sanction
        fields = [
            'id', 'user', 'user_name', 'sanction_type', 'reason', 'related_post',
            'issued_by_name', 'is_active', 'starts_at', 'ends_at', 'created_at',
        ]
        read_only_fields = ['is_active', 'starts_at', 'created_at']

    def validate_related_post(self, value):
        if value is not None and not marketplace_services.offer_exists(value):
            raise serializers.ValidationError("Annonce introuvable.")
        return value

    def validate(self, attrs):
        if attrs.get('sanction_type') == Sanction.TYPE_MASQUAGE_ANNONCE and not attrs.get('related_offer_id'):
            raise serializers.ValidationError(
                {'related_post': "related_post est requis pour un masquage d'annonce."}
            )
        return attrs
