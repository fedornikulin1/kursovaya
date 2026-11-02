"""Validate decoded images, rather than trusting an extension or Content-Type."""

from PIL import Image, UnidentifiedImageError
from django.core.exceptions import ValidationError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_IMAGES = 8


def validate_image(value):
    if value.size > MAX_IMAGE_BYTES:
        raise ValidationError("Фотография должна быть не больше 5 МБ.")
    try:
        value.seek(0)
        with Image.open(value) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Разрешены фотографии JPEG, PNG и WebP.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValidationError("Разрешение фотографии слишком большое (максимум 24 Мп).")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise ValidationError("Не удалось прочитать изображение.") from exc
    finally:
        value.seek(0)
