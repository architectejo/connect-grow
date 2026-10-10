"""Fabriques de données pour les tests (aucun import d'un domaine métier)."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def make_test_image(name='photo.jpg', color=(255, 0, 0), fmt='JPEG', size=(20, 20), exif=None):
    """Image valide en mémoire, prête à être envoyée par l'API ou assignée à un ImageField."""
    buffer = io.BytesIO()
    image = Image.new('RGB', size, color=color)
    save_args = {'format': fmt}
    if exif is not None:
        save_args['exif'] = exif
    image.save(buffer, **save_args)
    buffer.seek(0)
    content_type = 'image/jpeg' if fmt == 'JPEG' else f'image/{fmt.lower()}'
    return SimpleUploadedFile(name, buffer.read(), content_type=content_type)
