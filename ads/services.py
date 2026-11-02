"""Business rules shared by HTML views and API endpoints."""

from io import BytesIO

from PIL import Image, ImageOps
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Ad, AdImage, Message, Response, Review, UserProfile
from .validators import MAX_IMAGES, validate_image


def profile_for(user):
    return UserProfile.objects.get_or_create(user=user)[0]


def normalized_image(upload):
    """Re-encode uploads: remove metadata, normalize orientation and cap dimensions."""
    validate_image(upload)
    upload.seek(0)
    with Image.open(upload) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((2000, 2000))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=86, optimize=True)
    return ContentFile(buffer.getvalue(), name="photo.jpg")


@transaction.atomic
def save_ad(*, ad, author, photos=(), delete_photos=()):
    if ad.pk and ad.author_id != author.pk:
        raise PermissionDenied("Изменять объявление может только автор.")
    if ad.pk:
        current = Ad.objects.select_for_update().get(pk=ad.pk)
        from campus.models import Meeting

        occupied = current.meetings.filter(
            Q(status__in=["transferred", "on_loan", "return_pending"])
            | Q(status="confirmed", ends_at__gt=timezone.now())
        ).exists()
        if occupied and any(
            getattr(ad, field) != getattr(current, field)
            for field in ("kind", "status", "available_from", "available_until", "campus_place_id")
        ):
            raise ValidationError(
                "Сначала завершите передачу или отмените встречу, прежде чем менять способ передачи, место, время или статус объявления."
            )
    ad.author = author
    delete_ids = {photo.pk if isinstance(photo, AdImage) else int(photo) for photo in delete_photos}
    owned_ids = (
        set(ad.images.filter(pk__in=delete_ids).values_list("pk", flat=True)) if ad.pk else set()
    )
    if owned_ids != delete_ids:
        raise PermissionDenied("Удалять можно только фотографии этого объявления.")
    existing_count = (ad.images.count() if ad.pk else 0) - len(delete_ids)
    if existing_count + bool(ad.image) + len(photos) > MAX_IMAGES:
        raise ValidationError(f"Можно загрузить не больше {MAX_IMAGES} фотографий.")
    for upload in photos:
        validate_image(upload)
    if ad.image and not ad.image._committed:
        ad.image = normalized_image(ad.image)
    ad.full_clean()
    ad.save()
    ad.images.filter(pk__in=delete_ids).delete()
    next_position = max(ad.images.values_list("position", flat=True), default=-1) + 1
    for index, upload in enumerate(photos, start=next_position):
        AdImage.objects.create(ad=ad, image=normalized_image(upload), position=index)
    return ad


@transaction.atomic
def start_conversation(*, ad, user, text):
    ad = Ad.objects.select_for_update().get(pk=ad.pk)
    if ad.author_id == user.pk:
        raise ValidationError("Это ваше объявление.")
    if ad.status != Ad.Status.ACTIVE:
        raise ValidationError("Объявление уже закрыто.")
    conversation, _ = Response.objects.get_or_create(ad=ad, user=user)
    send_message(conversation=conversation, sender=user, text=text)
    return conversation


@transaction.atomic
def delete_ad(*, ad, user):
    ad = Ad.objects.select_for_update().get(pk=ad.pk)
    if ad.author_id != user.pk:
        raise PermissionDenied
    from campus.models import Meeting
    from campus.services import expire_meetings

    expire_meetings(ad)
    if ad.meetings.filter(status__in=Meeting.LIVE).exists():
        raise ValidationError(
            "Сначала завершите передачу или отмените встречу. Во время брони и временной передачи удалить объявление нельзя."
        )
    ad.delete()


@transaction.atomic
def send_message(*, conversation, sender, text):
    if sender.pk not in (conversation.user_id, conversation.ad.author_id):
        raise PermissionDenied("Этот диалог вам недоступен.")
    text = text.strip()
    if not text or len(text) > 4000:
        raise ValidationError("Сообщение должно содержать от 1 до 4000 символов.")
    message = Message.objects.create(response=conversation, sender=sender, text=text)
    Response.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
    return message


def mark_read(conversation, user):
    if user.pk not in (conversation.user_id, conversation.ad.author_id):
        raise PermissionDenied
    conversation.messages.filter(read_at__isnull=True).exclude(sender=user).update(
        read_at=timezone.now()
    )


@transaction.atomic
def create_review(*, author, recipient, rating, text=""):
    if author.pk == recipient.pk:
        raise ValidationError("Нельзя оставить отзыв самому себе.")
    # Serialize review creation for a recipient to make the duplicate check reliable.
    type(recipient).objects.select_for_update().get(pk=recipient.pk)
    if Review.objects.filter(from_user=author, to_user=recipient).exists():
        raise ValidationError("Вы уже оставили отзыв этому пользователю.")
    from django.db.models import Q

    interaction = (
        Response.objects.filter(is_accepted=True)
        .filter(Q(user=author, ad__author=recipient) | Q(user=recipient, ad__author=author))
        .first()
    )
    if not interaction:
        raise ValidationError("Отзыв доступен после принятия отклика автором объявления.")
    review = Review(
        from_user=author, to_user=recipient, response=interaction, rating=rating, text=text
    )
    review.full_clean()
    review.save()
    return review
