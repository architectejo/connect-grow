"""Contrôle des pièces KYC déposées : type réel (octets de signature, jamais le nom
ni le Content-Type annoncé par le client), taille maximale configurable, nom de
stockage généré côté serveur."""
import uuid
from collections import namedtuple

from django.conf import settings
from django.core.exceptions import ValidationError

KycFileType = namedtuple('KycFileType', 'extension content_type')

# (signature en début de fichier, type)
SIGNATURES = (
    (b'\xff\xd8\xff', KycFileType('jpg', 'image/jpeg')),
    (b'\x89PNG\r\n\x1a\n', KycFileType('png', 'image/png')),
    (b'%PDF-', KycFileType('pdf', 'application/pdf')),
)
HEADER_LENGTH = max(len(signature) for signature, _ in SIGNATURES)

EXTENSION_TO_CONTENT_TYPE = {t.extension: t.content_type for _, t in SIGNATURES}


def detect_kyc_file_type(file):
    """Type détecté par le contenu (JPEG, PNG, PDF) ou None. Laisse le curseur en place."""
    position = file.tell() if hasattr(file, 'tell') else 0
    try:
        file.seek(0)
        header = file.read(HEADER_LENGTH)
    finally:
        file.seek(position)
    for signature, file_type in SIGNATURES:
        if header.startswith(signature):
            return file_type
    return None


def validate_kyc_file(file):
    """Validateur de champ : taille maximale puis type réel autorisé."""
    max_bytes = settings.KYC_MAX_FILE_BYTES
    if file.size > max_bytes:
        raise ValidationError(
            "Le fichier dépasse la taille maximale de %(max)s Mo.", params={'max': max_bytes // (1024 * 1024)},
            code='file_too_large',
        )
    if file.size == 0 or detect_kyc_file_type(file) is None:
        raise ValidationError("Format non accepté. Envoyez un fichier JPEG, PNG ou PDF.", code='invalid_file_type')


def kyc_upload_to(instance, filename):
    """Nom de stockage généré côté serveur : jamais le nom fourni par l'utilisateur."""
    file_type = detect_kyc_file_type(instance.file.file) if instance.file else None
    extension = file_type.extension if file_type else 'bin'
    return f"{uuid.uuid4().hex}.{extension}"
