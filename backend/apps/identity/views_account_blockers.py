"""`GET me/account-deletion-blockers/` (L1-01k, ADR 0008) : raisons pour lesquelles le compte appelant ne pourrait pas
être supprimé. Lecture seule ; la décision vient de `organizations.account_removal_blockers`, la même que celle de
`assert_account_removable`. Aucune écriture d'audit en lecture (ADR 0008, décision n°9). Ignore `X-Context`."""
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .organizations import account_removal_blockers
from .throttles import AccountBlockersThrottle

# Borne de la liste (comme `contexts/`) : jamais plus de 100 organisations, réponse non paginée.
MAX_BLOCKERS = 100

BLOCKERS_SCHEMA = inline_serializer('AccountDeletionBlockers', {
    'organizations': inline_serializer('AccountDeletionOrganizationBlocker', {
        'organization_id': serializers.UUIDField(),
        'name': serializers.CharField(),
        'status': serializers.ChoiceField(choices=['ACTIVE', 'SUSPENDED']),
        'other_members_count': serializers.IntegerField(),
        'suggested_action': serializers.ChoiceField(
            choices=['transfer_ownership', 'archive', 'wait_for_unsuspension'],
        ),
    }, many=True),
    'has_other_blocker': serializers.BooleanField(),
})


class AccountDeletionBlockersView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AccountBlockersThrottle]

    @extend_schema(operation_id='me_account_deletion_blockers', responses=BLOCKERS_SCHEMA)
    def get(self, request):
        blockers = account_removal_blockers(request.user, limit=MAX_BLOCKERS)
        response = Response({
            'organizations': [
                {
                    'organization_id': str(row.organization_id), 'name': row.name, 'status': row.status,
                    'other_members_count': row.other_members_count, 'suggested_action': row.suggested_action,
                }
                for row in blockers.organizations
            ],
            'has_other_blocker': blockers.other_code is not None,
        })
        response['Cache-Control'] = 'private, no-store'
        return response
