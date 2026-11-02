"""All meeting mutations lock the listing, shared by HTML and the mobile API."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from ads.models import Ad, Response
from ads.services import send_message
from .models import Meeting, StudyRequest


def require_participant(conversation, user):
    if user.pk not in (conversation.user_id, conversation.ad.author_id):
        raise PermissionDenied("Встреча доступна только участникам разговора.")


def expire_meetings(ad):
    # Called only inside write transactions after locking this listing. Reads stay read-only.
    Meeting.objects.filter(
        ad=ad, status__in=["proposed", "confirmed"], ends_at__lte=timezone.now()
    ).update(status=Meeting.Status.EXPIRED, updated_at=timezone.now())


@transaction.atomic
def propose_meeting(
    *, conversation, user, place, starts_at, ends_at, return_on=None, study_request=None
):
    ad = Ad.objects.select_for_update().get(pk=conversation.ad_id)
    require_participant(conversation, user)
    expire_meetings(ad)
    now = timezone.now()
    if ad.status != Ad.Status.ACTIVE:
        raise ValidationError("Объявление уже закрыто.")
    if not place.is_active:
        raise ValidationError("Это место больше недоступно.")
    if (
        starts_at <= now
        or ends_at <= starts_at
        or ends_at - starts_at > timedelta(hours=4)
        or ends_at > now + timedelta(days=30)
    ):
        raise ValidationError(
            "Выберите будущую встречу в ближайшие 30 дней, интервалом до 4 часов."
        )
    if ad.available_from and (starts_at < ad.available_from or ends_at > ad.available_until):
        raise ValidationError("Встреча должна попадать в интервал, указанный автором объявления.")
    if Meeting.objects.filter(ad=ad, status__in=Meeting.LIVE).exists():
        raise ValidationError("Вещь уже забронирована или передана. Дождитесь освобождения брони.")
    if Meeting.objects.filter(conversation=conversation, status=Meeting.Status.PROPOSED).exists():
        raise ValidationError("В разговоре уже есть предложение встречи. Сначала отмените его.")
    if study_request:
        if study_request.author_id != conversation.user_id or not study_request.is_active:
            raise ValidationError("Можно привязать только открытый запрос получателя.")
    is_loan = ad.kind == Ad.Kind.LEND
    if is_loan:
        meeting_date = timezone.localtime(ends_at).date()
        if not return_on or not meeting_date < return_on <= meeting_date + timedelta(days=180):
            raise ValidationError("Укажите возврат после встречи, не позднее чем через 180 дней.")
    elif return_on:
        raise ValidationError("Дата возврата нужна только для временной передачи.")
    meeting = Meeting.objects.create(
        conversation=conversation,
        ad=ad,
        proposed_by=user,
        place=place,
        starts_at=starts_at,
        ends_at=ends_at,
        return_on=return_on,
        is_loan=is_loan,
        study_request=study_request,
    )
    when = timezone.localtime(starts_at).strftime("%d.%m.%Y %H:%M")
    send_message(
        conversation=conversation,
        sender=user,
        text=f"Предлагаю встречу: {place.name}, {when}. Подтвердите её в карточке встречи. Бронь появится после подтверждения.",
    )
    return meeting


@transaction.atomic
def meeting_action(*, meeting, user, action):
    ad = Ad.objects.select_for_update().get(pk=meeting.ad_id)
    meeting = Meeting.objects.select_for_update().select_related("conversation").get(pk=meeting.pk)
    conversation = meeting.conversation
    require_participant(conversation, user)
    expire_meetings(ad)
    meeting.refresh_from_db()
    seller = user.pk == ad.author_id
    state = meeting.status
    if action == "confirm":
        if state != Meeting.Status.PROPOSED or meeting.proposed_by_id == user.pk:
            raise ValidationError("Предложение должен подтвердить другой участник.")
        if ad.status != Ad.Status.ACTIVE or not meeting.place.is_active:
            raise ValidationError("Объявление или место встречи больше недоступно.")
        if ad.available_from and (
            meeting.starts_at < ad.available_from or meeting.ends_at > ad.available_until
        ):
            raise ValidationError(
                "Автор изменил удобное время. Отмените предложение и выберите новый интервал."
            )
        if Meeting.objects.filter(ad=ad, status__in=Meeting.LIVE).exists():
            raise ValidationError("Вещь уже забронирована в другом разговоре.")
        meeting.status = Meeting.Status.CONFIRMED
        text = "Встреча подтверждена. Вещь забронирована до конца согласованного интервала."
    elif action == "cancel":
        if state not in (Meeting.Status.PROPOSED, Meeting.Status.CONFIRMED):
            raise ValidationError("Эту встречу уже нельзя отменить: проверьте статус передачи.")
        meeting.status = Meeting.Status.CANCELLED
        text = "Встреча отменена. Бронь освобождена."
    elif action == "handover":
        if not seller or state != Meeting.Status.CONFIRMED:
            raise ValidationError("Передачу может отметить автор после согласования встречи.")
        if timezone.now() < meeting.starts_at:
            raise ValidationError("Отметить передачу можно после начала встречи.")
        meeting.status = Meeting.Status.TRANSFERRED
        text = "Автор отметил передачу вещи. Получатель, подтвердите получение в карточке встречи."
    elif action == "receive":
        if seller or state != Meeting.Status.TRANSFERRED:
            raise ValidationError("Получение подтверждает получатель после отметки автора.")
        meeting.status = Meeting.Status.ON_LOAN if meeting.is_loan else Meeting.Status.COMPLETED
        conversation.is_accepted = True
        conversation.save(update_fields=["is_accepted", "updated_at"])
        if not meeting.is_loan:
            ad.status = Ad.Status.CLOSED
            ad.save(update_fields=["status", "updated_at"])
        if meeting.study_request_id:
            StudyRequest.objects.filter(pk=meeting.study_request_id).update(is_active=False)
        text = "Получение подтверждено. " + (
            f"Верните вещь до {meeting.return_on:%d.%m.%Y}."
            if meeting.is_loan
            else "Передача завершена, объявление закрыто."
        )
    elif action == "return":
        if seller or state != Meeting.Status.ON_LOAN:
            raise ValidationError("Возврат отмечает получатель вещи, взятой на время.")
        meeting.status = Meeting.Status.RETURN_PENDING
        text = "Получатель отметил возврат. Автор, подтвердите, что вещь снова у вас."
    elif action == "finish_return":
        if not seller or state != Meeting.Status.RETURN_PENDING:
            raise ValidationError("Возврат должен подтвердить автор вещи.")
        meeting.status = Meeting.Status.COMPLETED
        text = "Автор подтвердил возврат. Вещь снова доступна для передачи."
    else:
        raise ValidationError("Неизвестное действие.")
    meeting.full_clean()
    meeting.save(update_fields=["status", "updated_at"])
    send_message(conversation=conversation, sender=user, text=text)
    return meeting


@transaction.atomic
def respond_to_request(*, study_request, ad, user):
    ad = Ad.objects.select_for_update().get(pk=ad.pk)
    need = StudyRequest.objects.select_for_update().get(pk=study_request.pk)
    if ad.author_id != user.pk:
        raise PermissionDenied("Предлагать можно только свои вещи.")
    if (
        not need.is_active
        or need.author_id == user.pk
        or ad.status != Ad.Status.ACTIVE
        or not ad.is_study
        or ad.kind in ("buy", "roommate")
    ):
        raise ValidationError(
            "Выберите своё опубликованное учебное предложение и чужой открытый запрос."
        )
    thread, created = Response.objects.get_or_create(ad=ad, user=need.author)
    if created:
        send_message(
            conversation=thread,
            sender=user,
            text=f"Предлагаю «{ad.title}» по вашему запросу «{need.title}». Обсудим передачу?",
        )
    return thread
