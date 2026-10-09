"""Ré-encodage des images envoyées par les utilisateurs (photos de profil, logos).

Le fichier est décodé puis ré-encodé en WebP : toutes les métadonnées (EXIF, dont la
position GPS, profils ICC, commentaires) sont perdues, l'orientation est appliquée aux
pixels, et les dimensions sont plafonnées (règle 10 : la position précise n'est jamais
publique). Les plafonds viennent des réglages Django.
"""
import io
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


def validate_image_upload_size(file):
    """Validateur de champ : taille maximale du fichier envoyé (PROFILE_IMAGE_MAX_BYTES)."""
    if file.size > settings.PROFILE_IMAGE_MAX_BYTES:
        raise ValidationError(
            "L'image dépasse la taille maximale de %(max)s Mo.",
            params={'max': settings.PROFILE_IMAGE_MAX_BYTES // (1024 * 1024)}, code='image_too_large',
        )


def reencode_image(uploaded_file) -> ContentFile:
    """Renvoie un ContentFile WebP sans métadonnées, redimensionné, au nom généré côté serveur.

    Lève ValidationError si le fichier n'est pas une image lisible ou dépasse le nombre de
    pixels autorisé (protection contre les images « bombes »)."""
    try:
        with Image.open(uploaded_file) as image:
            if image.width * image.height > settings.PROFILE_IMAGE_MAX_PIXELS:
                raise ValidationError("Les dimensions de l'image sont trop grandes.", code='image_too_large')
            image = ImageOps.exif_transpose(image)  # orientation appliquée, balise EXIF abandonnée
            has_alpha = image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info)
            image = image.convert('RGBA' if has_alpha else 'RGB')
            max_side = settings.PROFILE_IMAGE_MAX_SIDE
            image.thumbnail((max_side, max_side))
            buffer = io.BytesIO()
            image.save(buffer, format='WEBP', quality=settings.PROFILE_IMAGE_QUALITY)  # aucun exif= transmis
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError("Fichier image invalide.", code='invalid_image')
    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.webp")


def sanitize_uploaded_field(field_file):
    """À appeler dans `save()` : si le champ image vient d'être renseigné (fichier pas encore
    stocké), renvoie son équivalent ré-encodé ; sinon renvoie la valeur inchangée."""
    if field_file and not getattr(field_file, '_committed', True):
        return reencode_image(field_file.file)
    return field_file
