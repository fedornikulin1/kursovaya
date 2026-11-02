"""Domain models shared by the web interface and API v1."""

import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse

from .validators import validate_image


def image_path(instance, filename):
    # Neutral path: advertising filters may block image URLs containing /ads/.
    return f"listings/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    bio = models.TextField("О себе", max_length=1000, blank=True)
    faculty = models.CharField("Институт / факультет", max_length=150, blank=True)
    group = models.CharField("Учебная группа", max_length=50, blank=True)
    role = models.CharField(
        "Статус",
        max_length=15,
        choices=[("student", "Студент"), ("staff", "Сотрудник")],
        default="student",
    )
    phone = models.CharField(
        "Телефон",
        max_length=16,
        blank=True,
        validators=[
            RegexValidator(
                r"^\+?[0-9]{7,15}$", "Введите номер без пробелов, например +79991234567."
            )
        ],
    )
    show_phone = models.BooleanField("Разрешить звонки по моим объявлениям", default=False)
    reduce_motion = models.BooleanField("Уменьшить анимации", default=False)
    telegram = models.CharField(
        "Telegram",
        max_length=32,
        blank=True,
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9_]{5,32}$", "Укажите имя Telegram без @, от 5 до 32 символов."
            )
        ],
    )

    def __str__(self):
        return self.user.username


class Category(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    icon = models.CharField("Иконка", max_length=24, default="grid")
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Ad(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ACTIVE = "active", "Опубликовано"
        CLOSED = "closed", "Закрыто"
        ARCHIVED = "archived", "В архиве"

    class Kind(models.TextChoices):
        SELL = "sell", "Продам"
        BUY = "buy", "Куплю"
        SERVICE = "service", "Услуга"
        ROOMMATE = "roommate", "Ищу соседа"
        EXCHANGE = "exchange", "Обменяю"
        GIVE = "give", "Отдам бесплатно"
        LEND = "lend", "Дам на время"

    class PriceType(models.TextChoices):
        FIXED = "fixed", "Фиксированная"
        FREE = "free", "Бесплатно"
        NEGOTIABLE = "negotiable", "Договорная"

    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", max_length=10000)
    price = models.DecimalField(
        "Цена",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    price_type = models.CharField(
        "Формат цены", max_length=15, choices=PriceType.choices, default=PriceType.FIXED
    )
    kind = models.CharField(
        "Тип объявления", max_length=15, choices=Kind.choices, default=Kind.SELL
    )
    status = models.CharField(
        "Статус", max_length=15, choices=Status.choices, default=Status.ACTIVE
    )
    image = models.ImageField(
        "Обложка", upload_to=image_path, blank=True, validators=[validate_image]
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="ads", verbose_name="Категория"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ads", verbose_name="Автор"
    )
    location = models.CharField("Место встречи", max_length=150, default="Кампус СВФУ")
    condition = models.CharField(
        "Состояние",
        max_length=15,
        choices=[("new", "Новое"), ("used", "Б/у"), ("na", "Не применимо")],
        default="used",
    )
    contact_info = models.CharField("Дополнительные контакты", max_length=200, blank=True)
    is_study = models.BooleanField("Для учебного обмена", default=False)
    subject = models.CharField("Предмет", max_length=120, blank=True)
    course = models.PositiveSmallIntegerField(
        "Курс", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    semester = models.PositiveSmallIntegerField(
        "Семестр", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    campus_place = models.ForeignKey(
        "campus.CampusPlace",
        verbose_name="Место в кампусе",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ads",
    )
    available_from = models.DateTimeField("Можно забрать с", null=True, blank=True)
    available_until = models.DateTimeField("Можно забрать до", null=True, blank=True)
    exchange_for = models.CharField("На что обменяю", max_length=200, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Объявление"
        verbose_name_plural = "Объявления"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "category", "-created_at"]),
            models.Index(fields=["status", "price"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__isnull=True) | Q(price__gte=0), name="ad_price_nonnegative"
            ),
            models.CheckConstraint(
                condition=(
                    Q(price_type="fixed", price__isnull=False, price__gte=0)
                    | Q(price_type="free", price__isnull=False, price=0)
                    | Q(price_type="negotiable", price__isnull=True)
                ),
                name="ad_price_matches_type",
            ),
        ]

    def clean(self):
        super().clean()
        from campus.models import validate_window

        validate_window(self.available_from, self.available_until)
        if self.is_study and not self.subject.strip():
            raise ValidationError({"subject": "Для учебного обмена укажите предмет."})
        if self.kind in (self.Kind.EXCHANGE, self.Kind.GIVE, self.Kind.LEND):
            self.price_type = self.PriceType.FREE
        if self.campus_place_id:
            self.location = self.campus_place.name
        if self.price_type == self.PriceType.FREE:
            self.price = 0
        elif self.price_type == self.PriceType.NEGOTIABLE:
            self.price = None
        elif self.price is None:
            raise ValidationError({"price": "Укажите цену или выберите другой формат цены."})

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("ads:ad_detail", kwargs={"pk": self.pk})

    @property
    def price_label(self):
        if self.kind == self.Kind.EXCHANGE:
            return "Обмен"
        if self.kind == self.Kind.LEND:
            return "На время · бесплатно"
        if self.price_type == self.PriceType.FREE:
            return "Бесплатно"
        if self.price_type == self.PriceType.NEGOTIABLE:
            return "Договорная"
        return f"{self.price:,.0f} ₽".replace(",", " ")

    @property
    def cover(self):
        return self.image or (self.images.all()[0].image if self.images.all() else None)


class AdImage(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("Фотография", upload_to=image_path, validators=[validate_image])
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "ad"], name="unique_favorite")]


class Response(models.Model):
    """One private conversation per interested user and listing.

    text/reply retain the original data; migration copies them into Message rows.
    New messages are written only to Message.
    """

    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="responses")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="responses"
    )
    text = models.TextField("Первый отклик (архив)", blank=True)
    reply = models.TextField("Ответ (архив)", blank=True)
    is_accepted = models.BooleanField("Отклик принят", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["ad", "user"], name="unique_ad_conversation")
        ]

    def __str__(self):
        return f"{self.user} → {self.ad}"


class Message(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    text = models.TextField("Сообщение", max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField("Прочитано", null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["response", "created_at"])]


class Review(models.Model):
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews_received",
        verbose_name="Кому",
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews_given",
        verbose_name="От кого",
    )
    response = models.ForeignKey(
        Response, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        "Оценка",
        choices=[(i, str(i)) for i in range(1, 6)],
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    text = models.TextField("Отзыв", max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        # Preserve the existing policy and all historic reviews.
        constraints = [
            models.UniqueConstraint(fields=["to_user", "from_user"], name="unique_user_review"),
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_5"
            ),
            models.CheckConstraint(condition=~Q(to_user=F("from_user")), name="review_not_self"),
        ]

    def __str__(self):
        return f"{self.from_user} → {self.to_user}: {self.rating}"
