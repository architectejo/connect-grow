from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Pagination par défaut des listes publiques (`?page=`, `?page_size=`)."""

    page_size_query_param = 'page_size'

    # Valeurs lues dans les réglages (API_PAGE_SIZE, API_MAX_PAGE_SIZE) ; un `page_size`
    # client est accepté mais plafonné ; hors plage (0, négatif, non numérique) : défaut.
    @property
    def page_size(self):
        return int(getattr(settings, 'API_PAGE_SIZE', 20))

    @property
    def max_page_size(self):
        return int(getattr(settings, 'API_MAX_PAGE_SIZE', 100))


class OptionalPagination(StandardPagination):
    """Pagination à la demande : sans `?page=` ni `?page_size=`, la liste reste un simple
    tableau (contrat historique du front) ; avec l'un des deux, enveloppe
    paginée standard (`count`, `next`, `previous`, `results`)."""

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if 'page' not in params and self.page_size_query_param not in params:
            return None
        return super().paginate_queryset(queryset, request, view)
