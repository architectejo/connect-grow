"""Contrôle des pièces KYC déposées : type réel (octets de signature, jamais le nom
ni le Content-Type annoncé par le client), taille maximale configurable, nom de
stockage généré côté serveur."""
import io
import re
import uuid
from collections import namedtuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

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


# Actifs dangereux d'un PDF (analyse d'octets, sans dépendance). Ne remplace pas un antivirus : un analyseur
# (ClamAV) reste un prérequis de production (ADR 0006, amendement T4).
PDF_FORBIDDEN_NAMES = (b'/JavaScript', b'/JS', b'/Launch', b'/EmbeddedFile', b'/OpenAction')
_PDF_NAME_ESCAPE = re.compile(rb'#([0-9A-Fa-f]{2})')
_PDF_NAME_END = rb'(?![A-Za-z0-9_.\-])'


def _unescape_pdf_names(raw):
    """Les noms PDF acceptent `#xx` (ex. `/J#61vaScript`) : on les décode avant la recherche."""
    return _PDF_NAME_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), raw)


def pdf_has_active_content(raw: bytes) -> bool:
    decoded = _unescape_pdf_names(raw)
    return any(re.search(re.escape(name) + _PDF_NAME_END, decoded) for name in PDF_FORBIDDEN_NAMES)


def _validate_image_content(file, file_type):
    """Ouvre vraiment l'image avec Pillow (`verify()` puis rechargement) et plafonne les pixels."""
    format_name = 'JPEG' if file_type.extension == 'jpg' else 'PNG'
    try:
        file.seek(0)
        with Image.open(file, formats=[format_name]) as image:
            width, height = image.size
            if width * height > settings.PROFILE_IMAGE_MAX_PIXELS:
                raise ValidationError("Les dimensions de l'image sont trop grandes.", code='image_too_large')
            image.verify()
        file.seek(0)
        with Image.open(file, formats=[format_name]) as image:
            image.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError("Format non accepté. Envoyez un fichier JPEG, PNG ou PDF.", code='invalid_file_type')
    finally:
        file.seek(0)


def _validate_pdf_content(file):
    file.seek(0)
    raw = file.read()
    file.seek(0)
    if pdf_has_active_content(raw):
        raise ValidationError("Ce PDF contient du contenu actif et n'est pas accepté.", code='pdf_active_content')


def sanitize_kyc_image(file, file_type):
    """JPEG ou PNG ré-encodé dans le MÊME format, sans métadonnées (EXIF, GPS, profils, commentaires) et sans
    redimensionnement : un justificatif doit rester lisible. Un PDF est renvoyé tel quel. Pas de WebP ici : le
    contrôle de type et le téléchargement reposent sur JPEG/PNG/PDF."""
    if file_type.extension == 'pdf':
        return file
    format_name = 'JPEG' if file_type.extension == 'jpg' else 'PNG'
    file.seek(0)
    with Image.open(file, formats=[format_name]) as image:
        image = ImageOps.exif_transpose(image)
        if format_name == 'JPEG':
            image = image.convert('RGB')
        elif image.mode not in ('RGB', 'RGBA', 'L', 'LA'):
            image = image.convert('RGBA' if 'transparency' in image.info or image.mode in ('PA', 'RGBa') else 'RGB')
        buffer = io.BytesIO()
        image.save(buffer, format=format_name, **({'quality': 92} if format_name == 'JPEG' else {}))
    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.{file_type.extension}")


def validate_kyc_file(file):
    """Validateur de champ : taille maximale, type réel autorisé, puis contenu (image lisible, PDF sans actif)."""
    max_bytes = settings.KYC_MAX_FILE_BYTES
    if file.size > max_bytes:
        raise ValidationError(
            "Le fichier dépasse la taille maximale de %(max)s Mo.", params={'max': max_bytes // (1024 * 1024)},
            code='file_too_large',
        )
    if file.size == 0 or detect_kyc_file_type(file) is None:
        raise ValidationError("Format non accepté. Envoyez un fichier JPEG, PNG ou PDF.", code='invalid_file_type')
    file_type = detect_kyc_file_type(file)
    if file_type.extension == 'pdf':
        _validate_pdf_content(file)
    else:
        _validate_image_content(file, file_type)


def kyc_upload_to(instance, filename):
    """Nom de stockage généré côté serveur : jamais le nom fourni par l'utilisateur."""
    file_type = detect_kyc_file_type(instance.file.file) if instance.file else None
    extension = file_type.extension if file_type else 'bin'
    return f"{uuid.uuid4().hex}.{extension}"
