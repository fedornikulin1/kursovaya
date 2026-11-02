"""The website, API and admin share these permission checks and state transitions."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import SupportMessage, SupportTicket


def can_answer(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.has_perm("support.change_supportticket")
    )


def clean_text(value, limit):
    value = value.strip()
    if not value or len(value) > limit:
        raise ValidationError(f"Введите текст от 1 до {limit} символов.")
    return value


@transaction.atomic
def create_ticket(*, user, subject, topic, text):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    # Serialize submissions from the same user, including the hourly limit.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    recent = SupportTicket.objects.filter(
        user=user, created_at__gte=timezone.now() - timedelta(hours=1)
    )
    if recent.count() >= 5:
        raise ValidationError(
            "Можно создать до 5 обращений в час. Продолжите существующее обращение или попробуйте позже."
        )
    ticket = SupportTicket(user=user, subject=clean_text(subject, 150), topic=topic)
    ticket.full_clean()
    ticket.save()
    SupportMessage.objects.create(ticket=ticket, sender=user, text=clean_text(text, 4000))
    return ticket


def authorize(ticket, actor, staff=False):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied
    if staff:
        if not can_answer(actor):
            raise PermissionDenied
    elif actor.pk != ticket.user_id:
        raise PermissionDenied


@transaction.atomic
def reply_ticket(*, ticket, actor, text, staff=False, close=False):
    ticket = SupportTicket.objects.select_for_update().get(pk=ticket.pk)
    authorize(ticket, actor, staff)
    if ticket.status == SupportTicket.Status.CLOSED:
        raise ValidationError("Сначала откройте обращение повторно.")
    message = SupportMessage.objects.create(
        ticket=ticket, sender=actor, from_staff=staff, text=clean_text(text, 4000)
    )
    ticket.status = (
        SupportTicket.Status.CLOSED
        if close and staff
        else SupportTicket.Status.ANSWERED if staff else SupportTicket.Status.OPEN
    )
    ticket.save(update_fields=["status", "updated_at"])
    return message


@transaction.atomic
def set_status(*, ticket, actor, closed, staff=False):
    ticket = SupportTicket.objects.select_for_update().get(pk=ticket.pk)
    authorize(ticket, actor, staff)
    ticket.status = SupportTicket.Status.CLOSED if closed else SupportTicket.Status.OPEN
    ticket.save(update_fields=["status", "updated_at"])
    return ticket


def mark_answers_read(ticket, user):
    authorize(ticket, user)
    ticket.messages.filter(from_staff=True, read_at__isnull=True).update(read_at=timezone.now())
