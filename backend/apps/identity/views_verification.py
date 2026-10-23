"""Pièces et état de vérification d'une organisation (ADR 0006, 9.4). Vues fines : logique dans `verification.py`.

L'organisation vient du chemin ; l'autorisation se fait d'après le rôle réel du demandeur dans CETTE
organisation, jamais d'après l'en-tête `X-Context` (ADR 6.4). Aucune réponse ne contient l'URL ni le contenu
d'un fichier : le téléchargement reste réservé à `review_kycdocument` (`kyc/documents/<uuid>/download/`)."""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.contexts import CONTEXT_ORGANIZATION
from apps.common.pagination import StandardPagination

from .serializers import OrganizationKycDocumentSerializer
from .services import (
    ActingContextMixin, delete_kyb_document, get_organization_verification, list_kyb_documents, submit_kyb_document,
)
from .throttles import KycWriteThrottle


def _private(response):
    response['Cache-Control'] = 'private, no-store'
    return response


class OrganizationKycDocumentListCreateView(ActingContextMixin, generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [KycWriteThrottle]
    serializer_class = OrganizationKycDocumentSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        # Pas d'autorisation par objet ici : elle refuserait une organisation suspendue/archivée, alors que la
        # lecture reste permise ; le service contrôle l'appartenance, le compte et la capacité.
        return list_kyb_documents(self.request.user, self.kwargs['org_id'])

    def list(self, request, *args, **kwargs):
        return _private(super().list(request, *args, **kwargs))

    def create(self, request, *args, **kwargs):
        self.authorize_object(CONTEXT_ORGANIZATION, self.kwargs['org_id'], 'org.verification_submit')
        data = request.data
        document = submit_kyb_document(
            request.user, self.kwargs['org_id'],
            data.get('document_type') if hasattr(data, 'get') else None, request.FILES.get('file'),
        )
        return _private(Response(OrganizationKycDocumentSerializer(document).data, status=status.HTTP_201_CREATED))


class OrganizationKycDocumentDeleteView(ActingContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [KycWriteThrottle]

    def delete(self, request, org_id, pk):
        self.authorize_object(CONTEXT_ORGANIZATION, org_id, 'org.verification_submit')
        delete_kyb_document(request.user, org_id, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationVerificationView(ActingContextMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, org_id):
        return _private(Response(get_organization_verification(request.user, org_id)))
