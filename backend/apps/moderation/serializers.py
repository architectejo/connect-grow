from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.common.exception_handler import CodedAPIException
from apps.marketplace import services as marketplace_services

from . import permissions, services
from .models import Report, Sanction

# Codes de cible exposés par l'API (contrat conservé jusqu'à L0-11) -> `target_type` stocké.
TARGET_TYPE_MAP = {
    'POST': 'offer',
    'REVIEW': 'review',
    'MESSAGE': 'message',
    'USER': 'user',
}
TARGET_TYPE_REVERSE = {v: k for k, v in TARGET_TYPE_MAP.items()}
# Champs renvoyés à l'auteur d'un signalement qui n'est pas du personnel de modération : jamais
# de libellé de cible (titre d'offre non publique, nom de compte), ni de notes de décision.
REPORTER_FIELDS = ('id', 'status', 'created_at')


class DuplicateReport(APIException):
    status_code = 409
    default_detail = "Signalement déjà déposé."
    default_code = 'duplicate_report'


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
            'decision_notes', 'created_at', 'resolved_at', 'author_response', 'author_responded_at',
        ]
        read_only_fields = [
            'status', 'decision_notes', 'created_at', 'resolved_at', 'author_response', 'author_responded_at',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is None or not permissions.can_moderate(request.user):
            return {key: data[key] for key in REPORTER_FIELDS}
        return data

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
        reporter = self.context['request'].user
        try:
            services.ensure_can_report(reporter, target_type, resolved[0], attrs.get('reason'))
        except services.ReportRefused as error:
            if error.code:
                raise CodedAPIException(str(error), error.code, error.status_code, wait=error.wait)
            if error.duplicate:
                raise DuplicateReport(str(error))
            raise serializers.ValidationError({'object_id': str(error)})
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

    def validate_user(self, user):
        if user.is_staff or user.is_superuser or user.pk == self.context['request'].user.pk:
            raise serializers.ValidationError(
                "Impossible de sanctionner un compte du personnel ou votre propre compte."
            )
        return user

    def validate(self, attrs):
        offer_id = attrs.get('related_offer_id')
        if offer_id and 'user' in attrs and not marketplace_services.seller_owns_offer(offer_id, attrs['user'].pk):
            raise serializers.ValidationError(
                {'related_post': "Cette annonce n'appartient pas à l'utilisateur sanctionné."}
            )
        if attrs.get('sanction_type') == Sanction.TYPE_MASQUAGE_ANNONCE and not attrs.get('related_offer_id'):
            raise serializers.ValidationError(
                {'related_post': "related_post est requis pour un masquage d'annonce."}
            )
        return attrs
