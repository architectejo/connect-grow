from django.utils.cache import patch_cache_control, patch_vary_headers


class ApiCacheHeadersMiddleware:
    """En-têtes de cache de l'API (L0-10a-a, règle 10) : une réponse d'`/api/` dépend de
    l'utilisateur (favori, masquage, droits). Aucun cache partagé ne doit la resservir à un tiers.

    - `Vary: Authorization` sur toute réponse de l'API (fusionné avec le `Vary` existant, CORS compris) ;
    - `Cache-Control: private` si la requête porte un jeton ou si la réponse pose un cookie.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/'):
            patch_vary_headers(response, ['Authorization'])
            if request.META.get('HTTP_AUTHORIZATION') or response.cookies:
                patch_cache_control(response, private=True)
        return response
