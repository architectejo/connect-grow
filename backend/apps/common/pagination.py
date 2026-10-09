from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Pagination par défaut des listes publiques (`?page=`, `?page_size=`)."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class OptionalPagination(StandardPagination):
    """Pagination à la demande : sans `?page=` ni `?page_size=`, la liste reste un simple
    tableau (contrat historique du front, jusqu'à L0-11) ; avec l'un des deux, enveloppe
    paginée standard (`count`, `next`, `previous`, `results`)."""

    def paginate_queryset(self, queryset, request, view=None):
        params = request.query_params
        if 'page' not in params and self.page_size_query_param not in params:
            return None
        return super().paginate_queryset(queryset, request, view)
