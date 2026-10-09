"""Format d'erreur de l'API : toute erreur non liée à un champ a pour corps
`{"detail": "<message en français>", "code": "<code_machine>"}` (ADR 0004, section 7).

Additif : les erreurs de validation de champs gardent le format DRF (`{"champ": ["message"]}`).
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class CodedAPIException(APIException):
    """Refus métier portant un code machine stable que le front peut interpréter."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail, code, status_code=None):
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=detail, code=code)


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and 'detail' in data and 'code' not in data and isinstance(exc, APIException):
        codes = exc.get_codes()
        code = codes.get('detail') if isinstance(codes, dict) else codes
        if isinstance(code, str):
            data['code'] = code
    return response
