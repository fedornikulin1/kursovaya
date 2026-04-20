from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Name")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name

class Ad(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(verbose_name="Описание")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    image = models.ImageField(upload_to='ads/', blank=True, null=True, verbose_name="Фотография")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='ads', verbose_name="Категория")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ads', verbose_name="Продавец")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано в")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    contact_info = models.CharField(max_length=200, blank=True, verbose_name="Контакты для связи", help_text="Телефон, Telegram, email")

    class Meta:
        verbose_name = "Ad"
        verbose_name_plural = "Ads"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('ad_detail', kwargs={'pk': self.pk})

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'ad']
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"

    def __str__(self):
        return f"{self.user.username} -> {self.ad.title}"

class Response(models.Model):
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='responses')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='responses')
    text = models.TextField(verbose_name="Текст отклика")
    created_at = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(default=False, verbose_name="Принят")
    reply = models.TextField(blank=True, verbose_name="Ответ автора")

    class Meta:
        verbose_name = "Response"
        verbose_name_plural = "Responses"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} -> {self.ad.title[:20]}"