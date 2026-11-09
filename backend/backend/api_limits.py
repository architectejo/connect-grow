"""Validation des réglages de pagination (API_PAGE_SIZE, API_MAX_PAGE_SIZE), lus au démarrage."""
from django.core.exceptions import ImproperlyConfigured


def parse_page_limits(raw_size, raw_max):
    """Retourne `(page_size, max_page_size)` entiers, 1 <= page_size <= max_page_size.

    Une valeur non numérique, nulle, négative, ou un `page_size` supérieur au plafond interrompt le démarrage
    avec un message explicite (mieux qu'une pagination silencieusement fausse en production)."""
    values = {}
    for name, raw in (('API_PAGE_SIZE', raw_size), ('API_MAX_PAGE_SIZE', raw_max)):
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ImproperlyConfigured(f"{name} doit être un entier supérieur ou égal à 1 (reçu : {raw!r}).")
        if value < 1:
            raise ImproperlyConfigured(f"{name} doit être un entier supérieur ou égal à 1 (reçu : {value}).")
        values[name] = value
    if values['API_PAGE_SIZE'] > values['API_MAX_PAGE_SIZE']:
        raise ImproperlyConfigured(
            f"API_PAGE_SIZE ({values['API_PAGE_SIZE']}) ne peut pas dépasser API_MAX_PAGE_SIZE "
            f"({values['API_MAX_PAGE_SIZE']})."
        )
    return values['API_PAGE_SIZE'], values['API_MAX_PAGE_SIZE']
