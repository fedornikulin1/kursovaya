"""Campus exchange requests and the bilateral handover lifecycle."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.urls import reverse


class CampusPlace(models.Model):
    name = models.CharField("Место", max_length=120, unique=True)
    meeting_hint = models.CharField("Ориентир для встречи", max_length=200, blank=True)
    is_active = models.BooleanField("Доступно для выбора", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Место в кампусе"
        verbose_name_plural = "Места в кампусе"

    def __str__(self):
        return self.name


class StudyRequest(models.Model):
    class Mode(models.TextChoices):
        ANY = "any", "Любой вариант"
        BUY = "buy", "Купить"
        EXCHANGE = "exchange", "Обменять"
        GIVE = "give", "Получить бесплатно"
        LEND = "lend", "Взять на время"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_requests"
    )
    title = models.CharField("Что нужно", max_length=160)
    subject = models.CharField("Предмет", max_length=120)
    course = models.PositiveSmallIntegerField(
        "Курс", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    semester = models.PositiveSmallIntegerField(
        "Семестр", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    mode = models.CharField("Как получить", max_length=12, choices=Mode.choices, default=Mode.ANY)
    description = models.TextField("Подробности", max_length=2000, blank=True)
    place = models.ForeignKey(
        CampusPlace, verbose_name="Удобное место", on_delete=models.PROTECT, null=True, blank=True
    )
    available_from = models.DateTimeField("Удобно встретиться с", null=True, blank=True)
    available_until = models.DateTimeField("До", null=True, blank=True)
    is_active = models.BooleanField("Поиск открыт", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Учебный запрос"
        verbose_name_plural = "Учебные запросы"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(available_from__isnull=True, available_until__isnull=True)
                    | Q(
                        available_from__isnull=False,
                        available_until__isnull=False,
                        available_until__gt=F("available_from"),
                    )
                ),
                name="study_request_time_order",
            )
        ]

    def clean(self):
        validate_window(self.available_from, self.available_until)

    def get_absolute_url(self):
        return reverse("campus:request_detail", args=[self.pk])

    def __str__(self):
        return self.title


def validate_window(start, end):
    if bool(start) != bool(end) or (start and end and end <= start):
        raise ValidationError(
            {"available_until": "Укажите начало и конец интервала; конец должен быть позже начала."}
        )


class Meeting(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Ждёт подтверждения"
        CONFIRMED = "confirmed", "Встреча согласована · вещь в брони"
        TRANSFERRED = "transferred", "Автор отметил передачу"
        ON_LOAN = "on_loan", "Вещь у получателя"
        RETURN_PENDING = "return_pending", "Ожидает подтверждения возврата"
        COMPLETED = "completed", "Завершено"
        CANCELLED = "cancelled", "Отменено"
        EXPIRED = "expired", "Время встречи истекло"

    LIVE = [Status.CONFIRMED, Status.TRANSFERRED, Status.ON_LOAN, Status.RETURN_PENDING]
    conversation = models.ForeignKey(
        "ads.Response", on_delete=models.CASCADE, related_name="meetings"
    )
    # Redundant FK permits a DB-level unique reservation across all conversations.
    ad = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="meetings")
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    study_request = models.ForeignKey(
        StudyRequest, null=True, blank=True, on_delete=models.SET_NULL
    )
    place = models.ForeignKey(CampusPlace, on_delete=models.PROTECT, verbose_name="Место встречи")
    starts_at = models.DateTimeField("Начало встречи")
    ends_at = models.DateTimeField("Конец интервала / срок брони")
    return_on = models.DateField("Вернуть до", null=True, blank=True)
    is_loan = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Встреча и передача"
        verbose_name_plural = "Встречи и передачи"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="meeting_time_order"
            ),
            models.CheckConstraint(
                condition=Q(is_loan=False) | Q(return_on__isnull=False),
                name="loan_requires_return_date",
            ),
            models.UniqueConstraint(
                fields=["ad"],
                condition=Q(status__in=["confirmed", "transferred", "on_loan", "return_pending"]),
                name="one_live_campus_reservation",
            ),
            models.UniqueConstraint(
                fields=["conversation"],
                condition=Q(status="proposed"),
                name="one_meeting_proposal_per_thread",
            ),
        ]

    @property
    def effective_status(self):
        if (
            self.status in (self.Status.PROPOSED, self.Status.CONFIRMED)
            and self.ends_at <= timezone.now()
        ):
            return self.Status.EXPIRED
        return self.status

    @property
    def status_label(self):
        return self.Status(self.effective_status).label

    @property
    def is_overdue(self):
        return (
            self.is_loan
            and self.status in (self.Status.ON_LOAN, self.Status.RETURN_PENDING)
            and self.return_on < timezone.localdate()
        )

    def __str__(self):
        return f"{self.ad} · {self.status_label}"
