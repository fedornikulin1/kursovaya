"""Confirmation codes shared by the web registration and the API."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import EmailConfirmation


@transaction.atomic
def send_confirmation(user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    EmailConfirmation.objects.update_or_create(
        user=user,
        defaults={"code_hash": make_password(code), "created_at": timezone.now(), "attempts": 0},
    )
    send_mail(
        "Код подтверждения ДоскаСВФУ",
        f"Ваш код подтверждения: {code}. Код действует 15 минут.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


@transaction.atomic
def confirm_email(user, code):
    challenge = EmailConfirmation.objects.select_for_update().filter(user=user).first()
    if not challenge or challenge.attempts >= 5 or challenge.created_at < timezone.now() - timedelta(minutes=15):
        return False
    challenge.attempts += 1
    challenge.save(update_fields=["attempts"])
    if not check_password(code, challenge.code_hash):
        return False
    user.is_active = True
    user.save(update_fields=["is_active"])
    challenge.delete()
    return True
