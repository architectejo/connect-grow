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


def owner_kwargs(owner, context_type='USER', created_by=None):
    """Arguments de propriétaire d'une offre ou d'un compteur de visibilité (sans import de modèle).

    - `owner_kwargs(user)` : contexte personnel, l'auteur est le compte ;
    - `owner_kwargs(profile, 'PROVIDER', created_by=user)` : profil prestataire ;
    - `owner_kwargs(organization, 'ORGANIZATION', created_by=user)` : organisation.

    Pour un compteur de visibilité, `created_by` n'existe pas : utiliser `counter_owner_kwargs`.
    """
    if context_type == 'USER':
        return {'seller_context_type': 'USER', 'seller_context_id': owner.pk, 'created_by': created_by or owner}
    return {'seller_context_type': context_type, 'seller_context_id': owner.pk, 'created_by': created_by}


def counter_owner_kwargs(owner, context_type='USER'):
    """Arguments de propriétaire d'un `DailyVisibilityCounter` (contexte seul, pas d'auteur)."""
    return {'seller_context_type': context_type, 'seller_context_id': owner.pk}
