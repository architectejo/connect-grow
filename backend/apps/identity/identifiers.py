"""Normalisation des identifiants (e-mail, téléphone) pour la LIMITATION de débit.

Sert uniquement à fabriquer des clés de compteurs : « +243 81-000 0000 », « 243810000000 » et
« +243810000000 » comptent pour le même numéro, et « Alice@X.com » pour « alice@x.com »,
afin qu'on ne contourne pas un plafond en variant l'écriture. N'altère jamais la valeur
stockée ni celle utilisée pour authentifier.
"""
import re

_SEPARATORS = re.compile(r'[\s\-.()]')


def normalize_phone(value: str) -> str:
    cleaned = _SEPARATORS.sub('', value)
    if cleaned.startswith('00'):
        cleaned = '+' + cleaned[2:]
    if cleaned.startswith('243'):
        cleaned = '+' + cleaned
    return cleaned


def normalize_identifier(value: str) -> str:
    value = value.strip()
    return value.lower() if '@' in value else normalize_phone(value)
