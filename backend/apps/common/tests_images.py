import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.common.images import reencode_image
from apps.identity.models import BusinessProfile, User


def jpeg_with_exif(size=(2400, 1200), orientation=None):
    """JPEG portant EXIF avec position GPS (et orientation éventuelle)."""
    image = Image.new('RGB', size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = 'AppareilTest'                     # Make
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = 'S', (4.0, 19.0, 30.0)           # latitude Kinshasa
    gps[3], gps[4] = 'E', (15.0, 18.0, 0.0)           # longitude
    if orientation:
        exif[0x0112] = orientation
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', exif=exif)
    return buffer.getvalue()


def upload(content, name='photo.jpg', content_type='image/jpeg'):
    return SimpleUploadedFile(name, content, content_type=content_type)


class ReencodeImageTests(TestCase):
    def test_source_has_exif_and_gps(self):
        source = Image.open(io.BytesIO(jpeg_with_exif()))
        self.assertTrue(source.getexif().get_ifd(0x8825))

    def test_output_has_no_metadata_and_is_resized_webp(self):
        result = reencode_image(upload(jpeg_with_exif()))
        self.assertRegex(result.name, r'^[0-9a-f]{32}\.webp$')
        raw = result.read()
        self.assertNotIn(b'Exif', raw)
        self.assertNotIn(b'AppareilTest', raw)
        output = Image.open(io.BytesIO(raw))
        self.assertEqual(output.format, 'WEBP')
        self.assertEqual(max(output.size), 1024)
        self.assertEqual(dict(output.getexif()), {})
        self.assertFalse({'exif', 'icc_profile', 'xmp'} & set(output.info))

    def test_orientation_is_applied_to_pixels(self):
        result = reencode_image(upload(jpeg_with_exif(size=(200, 100), orientation=6)))
        output = Image.open(io.BytesIO(result.read()))
        self.assertEqual(output.size, (100, 200))

    def test_rejects_non_images_and_oversized_pixel_counts(self):
        with self.assertRaises(ValidationError):
            reencode_image(upload(b'MZ pas une image'))
        with self.settings(PROFILE_IMAGE_MAX_PIXELS=100):
            with self.assertRaises(ValidationError):
                reencode_image(upload(jpeg_with_exif(size=(50, 50))))


class ProfileImagesAreSanitizedTests(TestCase):
    def stored_exif(self, field_file):
        with Image.open(field_file.path) as stored:
            return dict(stored.getexif()), stored.format

    def test_user_photo_is_stored_without_exif(self):
        user = User.objects.create_user(email='p@example.com', password='x', full_name='P')
        user.photo = upload(jpeg_with_exif())
        user.save()
        exif, fmt = self.stored_exif(user.photo)
        self.assertEqual((exif, fmt), ({}, 'WEBP'))
        self.assertNotIn('photo.jpg', user.photo.name)

    def test_business_logo_is_stored_without_exif(self):
        owner = User.objects.create_user(email='b@example.com', password='x', full_name='B')
        profile = BusinessProfile.objects.create(user=owner, business_name='B', logo=upload(jpeg_with_exif()))
        exif, fmt = self.stored_exif(profile.logo)
        self.assertEqual((exif, fmt), ({}, 'WEBP'))

    def test_api_upload_of_organization_logo_strips_gps(self):
        from apps.identity.models import Organization

        user = User.objects.create_user(email='orglogo@example.com', password='x', full_name='A', phone_verified=True)
        client = APIClient()
        client.force_authenticate(user)
        response = client.post(
            '/api/accounts/organizations/',
            {'name': 'Logo Orga', 'org_type': 'ENTREPRISE', 'logo': upload(jpeg_with_exif())}, format='multipart',
        )
        self.assertEqual(response.status_code, 201, response.content)
        organization = Organization.objects.get(name='Logo Orga')
        self.assertEqual(self.stored_exif(organization.logo), ({}, 'WEBP'))

    def test_api_upload_of_photo_strips_gps(self):
        user = User.objects.create_user(email='api@example.com', password='x', full_name='A')
        client = APIClient()
        client.force_authenticate(user)
        response = client.patch('/api/accounts/me/', {'photo': upload(jpeg_with_exif())}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertEqual(self.stored_exif(user.photo)[0], {})

    def test_api_rejects_fake_and_oversized_images(self):
        user = User.objects.create_user(email='api@example.com', password='x', full_name='A')
        client = APIClient()
        client.force_authenticate(user)
        fake = client.patch('/api/accounts/me/', {'photo': upload(b'<script>alert(1)</script>')}, format='multipart')
        self.assertEqual(fake.status_code, 400)
        with self.settings(PROFILE_IMAGE_MAX_BYTES=100):
            big = client.patch('/api/accounts/me/', {'photo': upload(jpeg_with_exif())}, format='multipart')
        self.assertEqual(big.status_code, 400)
        self.assertIn('photo', big.data)

    def test_unchanged_photo_is_not_reencoded_on_later_saves(self):
        user = User.objects.create_user(email='p@example.com', password='x', full_name='P')
        user.photo = upload(jpeg_with_exif())
        user.save()
        name = user.photo.name
        user.full_name = 'Renommé'
        user.save()
        self.assertEqual(user.photo.name, name)


class PixelLimitTests(TestCase):
    def png(self, size):
        buffer = io.BytesIO()
        Image.new('RGB', size, (10, 10, 10)).save(buffer, format='PNG')
        return buffer.getvalue()

    def test_oversized_png_is_a_400_never_a_500_for_photo_and_logo(self):
        owner = User.objects.create_user(email='big@example.com', password='x', full_name='B', phone_verified=True)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(owner)
        with self.settings(PROFILE_IMAGE_MAX_PIXELS=1000):
            photo = client.patch('/api/accounts/me/', {'photo': upload(self.png((50, 50)), 'p.png', 'image/png')}, format='multipart')
            logo = client.post(
                '/api/accounts/organizations/',
                {'name': 'Grande boîte', 'org_type': 'ENTREPRISE', 'logo': upload(self.png((50, 50)), 'l.png', 'image/png')},
                format='multipart',
            )
        self.assertEqual(photo.status_code, 400, photo.content)
        self.assertIn('photo', photo.data)
        self.assertEqual(logo.status_code, 400, logo.content)
        self.assertIn('logo', logo.json())

    def test_image_within_limit_is_accepted(self):
        user = User.objects.create_user(email='ok@example.com', password='x', full_name='O')
        client = APIClient()
        client.force_authenticate(user)
        response = client.patch('/api/accounts/me/', {'photo': upload(self.png((20, 20)), 'p.png', 'image/png')}, format='multipart')
        self.assertEqual(response.status_code, 200)

    def test_pixel_validator_does_not_decode_and_rewinds_the_file(self):
        from apps.common.images import validate_image_pixels

        file = upload(self.png((30, 30)), 'p.png', 'image/png')
        validate_image_pixels(file)
        self.assertEqual(file.tell(), 0)

    def test_non_whitelisted_formats_are_refused(self):
        from apps.common.images import validate_image_pixels

        buffer = io.BytesIO()
        Image.new('RGB', (10, 10)).save(buffer, format='BMP')
        with self.assertRaises(ValidationError):
            validate_image_pixels(upload(buffer.getvalue(), 'x.bmp', 'image/bmp'))
        with self.assertRaises(ValidationError):
            reencode_image(upload(buffer.getvalue(), 'x.bmp', 'image/bmp'))

    def test_admin_form_rejects_oversized_image_instead_of_crashing(self):
        from django.core.exceptions import ValidationError as DjangoValidationError

        field = User._meta.get_field('photo')
        with self.settings(PROFILE_IMAGE_MAX_PIXELS=1000):
            with self.assertRaises(DjangoValidationError):
                field.clean(upload(self.png((50, 50)), 'p.png', 'image/png'), None)

    def test_pillow_pixel_ceiling_is_explicit(self):
        self.assertEqual(Image.MAX_IMAGE_PIXELS, 16_000_000)
