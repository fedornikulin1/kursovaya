"""Independent support conversations; marketplace chats remain private to their participants."""

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models
from django.urls import reverse


class SupportTicket(models.Model):
    class Topic(models.TextChoices):
        ACCOUNT = "account", "Аккаунт и вход"
        LISTING = "listing", "Объявления"
        MESSAGES = "messages", "Сообщения"
        SAFETY = "safety", "Безопасность"
        IDEA = "idea", "Идея для сайта"
        OTHER = "other", "Другой вопрос"

    class Status(models.TextChoices):
        OPEN = "open", "Ожидает поддержки"
        ANSWERED = "answered", "Поддержка ответила"
        CLOSED = "closed", "Закрыто"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_tickets",
        verbose_name="Автор",
    )
    subject = models.CharField("Тема обращения", max_length=150)
    topic = models.CharField("Раздел", max_length=20, choices=Topic.choices, default=Topic.OTHER)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        verbose_name = "Обращение"
        verbose_name_plural = "Обращения в поддержку"
        indexes = [models.Index(fields=["status", "updated_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["open", "answered", "closed"]),
                name="support_valid_status",
            )
        ]

    def __str__(self):
        return f"№ {self.pk} · {self.subject}"

    def get_absolute_url(self):
        return reverse("support:ticket", args=[self.pk])


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="support_messages",
        verbose_name="Автор",
    )
    from_staff = models.BooleanField("Ответ поддержки", default=False)
    text = models.TextField("Сообщение", max_length=4000, validators=[MaxLengthValidator(4000)])
    created_at = models.DateTimeField("Отправлено", auto_now_add=True)
    read_at = models.DateTimeField("Прочитано пользователем", null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Сообщение поддержки"
        verbose_name_plural = "Сообщения поддержки"


class FAQ(models.Model):
    topic = models.CharField("Раздел", max_length=20, choices=SupportTicket.Topic.choices)
    question = models.CharField("Вопрос", max_length=200)
    answer = models.TextField("Ответ", max_length=5000)
    is_published = models.BooleanField("Опубликован", default=True)
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = "Частый вопрос"
        verbose_name_plural = "Частые вопросы"

    def __str__(self):
        return self.question
