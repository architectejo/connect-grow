"""Réglages de la documentation OpenAPI (drf-spectacular, ADR 0007) : structure seulement, aucune donnée."""

CONTEXT_HEADER_NAME = 'X-Context'
CONTEXT_PARAMETER = 'ActiveContext'


def only_v1_endpoints(endpoints, **kwargs):
    """Ne garde que les routes de l'API versionnée `/api/v1/` (hors admin, schéma et documentation)."""
    skipped = ('/api/v1/schema/', '/api/v1/docs/')
    return [e for e in endpoints if e[0].startswith('/api/v1/') and not e[0].startswith(skipped)]


def add_context_header(result, generator, request, public):
    """Déclare `X-Context` (format `TYPE:uuid`) comme paramètre d'en-tête optionnel de chaque opération."""
    components = result.setdefault('components', {})
    components.setdefault('parameters', {})[CONTEXT_PARAMETER] = {
        'in': 'header',
        'name': CONTEXT_HEADER_NAME,
        'required': False,
        'schema': {'type': 'string', 'pattern': '^[A-Z_]+:[0-9a-fA-F-]{36}$'},
        'description': (
            "Contexte actif de la requête, au format `TYPE:uuid` (ex. `ORGANIZATION:<uuid>`). "
            "Absent : contexte personnel."
        ),
    }
    ref = {'$ref': f'#/components/parameters/{CONTEXT_PARAMETER}'}
    for item in result.get('paths', {}).values():
        for method, operation in item.items():
            if method in ('get', 'post', 'put', 'patch', 'delete'):
                operation.setdefault('parameters', []).append(ref)
    return result


from drf_spectacular.openapi import AutoSchema  # noqa: E402
from rest_framework import serializers  # noqa: E402
from rest_framework.generics import GenericAPIView  # noqa: E402


class PayloadLibre(serializers.Serializer):
    """Charge utile non décrite champ par champ (vue APIView sans serializer) : objet JSON libre."""


class ConnecteAutoSchema(AutoSchema):
    """Une vue `APIView` sans serializer est documentée comme objet libre au lieu d'une erreur.

    Dette : décrire ces charges utiles avec `extend_schema` au fil des stories (le comportement des vues
    n'est pas modifié)."""

    def _get_serializer(self):
        view = self.view
        if not isinstance(view, GenericAPIView) and not any(
            callable(getattr(view, name, None)) or hasattr(view, name)
            for name in ('get_serializer', 'get_serializer_class', 'serializer_class')
        ):
            return PayloadLibre()
        return super()._get_serializer()
