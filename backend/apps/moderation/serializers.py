from rest_framework import serializers

from apps.marketplace import services as marketplace_services

from . import services
from .models import Report, Sanction

# Codes de cible exposés par l'API (contrat conservé jusqu'à L0-11) -> `target_type` stocké.
TARGET_TYPE_MAP = {
    'POST': 'offer',
    'REVIEW': 'review',
    'MESSAGE': 'message',
    'USER': 'user',
}
TARGET_TYPE_REVERSE = {v: k for k, v in TARGET_TYPE_MAP.items()}


class ReportSerializer(serializers.ModelSerializer):
    target_type = serializers.ChoiceField(choices=list(TARGET_TYPE_MAP.keys()), write_only=True)
    target_type_display = serializers.SerializerMethodField()
    # Clé JSON `object_id` conservée jusqu'à L0-11 : UUID de la cible.
    object_id = serializers.CharField(source='target_id')
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
        return TARGET_TYPE_REVERSE.get(obj.target_type)

    def get_target_display(self, obj):
        # `target_labels` : libellés résolus par lot par la vue de liste (évite une requête par ligne).
        labels = self.context.get('target_labels')
        if labels is None:
            labels = services.resolve_labels_for_reports([obj])
        return labels.get((obj.target_type, obj.target_id))

    def validate(self, attrs):
        target_type = TARGET_TYPE_MAP[attrs.pop('target_type')]
        resolved = services.resolve_target(target_type, attrs['target_id'])
        if resolved is None:
            raise serializers.ValidationError({'object_id': "Cible introuvable."})
        # Forme canonique de la clé (UUID) : un même objet signalé sous plusieurs écritures
        # reste regroupé.
        attrs['target_type'] = target_type
        attrs['target_id'] = resolved[0]
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
