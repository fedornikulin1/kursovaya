import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from ads.models import Ad, Category, UserProfile
from campus.models import CampusMessage, Dormitory


@override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"])
class DormitoryFlowsTests(TestCase):
    def setUp(self):
        self.dorm = Dormitory.objects.create(name="Тестовое общежитие")
        self.other = Dormitory.objects.create(name="Другое общежитие")

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_registration_requires_email_code_when_enabled(self):
        response = self.client.post("/register/", {
            "username": "newperson", "first_name": "Фёдор", "email": "new@example.com",
            "dormitory": self.dorm.pk, "password1": "Strong!Pass123", "password2": "Strong!Pass123",
        })
        self.assertRedirects(response, "/register/confirm/")
        user = get_user_model().objects.get(username="newperson")
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.dormitory, self.dorm)
        self.assertFalse(self.client.login(username="newperson", password="Strong!Pass123"))
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()
        self.assertEqual(self.client.post("/register/confirm/", {"code": "999999"}).status_code, 200)
        self.assertRedirects(self.client.post("/register/confirm/", {"code": code}), "/accounts/login/")
        self.assertTrue(self.client.login(username="newperson", password="Strong!Pass123"))

    def test_room_feed_and_wanted_filter_are_isolated(self):
        user = get_user_model().objects.create_user(username="reader", password="Strong!Pass123")
        self.client.force_login(user)
        CampusMessage.objects.create(author=user, body="Общее сообщение")
        CampusMessage.objects.create(author=user, body="Ищу линейку", kind="wanted", dormitory=self.dorm)
        CampusMessage.objects.create(author=user, body="В другом общежитии", dormitory=self.other)
        response = self.client.get(f"/campus/chat/?room={self.dorm.pk}&view=wanted")
        self.assertContains(response, "Ищу линейку")
        self.assertNotContains(response, "В другом общежитии")
        response = self.client.get(f"/campus/chat/feed/?room={self.dorm.pk}&after=0")
        self.assertIn("Ищу линейку", response.json()["html"])
        self.assertNotIn("Общее сообщение", response.json()["html"])

    def test_catalog_prioritizes_same_dormitory(self):
        user = get_user_model().objects.create_user(username="resident", password="Strong!Pass123")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.dormitory = self.dorm
        profile.save()
        category = Category.objects.create(name="Категория")
        Ad.objects.create(author=user, category=category, title="Рядом", description="Рядом", price=1, dormitory=self.dorm)
        Ad.objects.create(author=user, category=category, title="Далеко", description="Далеко", price=1, dormitory=self.other)
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertEqual([ad.title for ad in response.context["ads"]], ["Рядом", "Далеко"])

    def test_food_shortcut_keeps_search_and_resets_page(self):
        user = get_user_model().objects.create_user(username="food-reader")
        UserProfile.objects.update_or_create(user=user, defaults={"dormitory": self.dorm})
        self.client.force_login(user)
        response = self.client.get("/?food=1&q=cola&page=1")
        self.assertContains(response, f'href="?food=1&amp;q=cola&amp;dormitory={self.dorm.pk}#catalog-results"')

        response = self.client.get("/", {"food": "1", "q": "cola", "dormitory": self.dorm.pk})
        self.assertNotContains(response, "Моё общежитие")
        self.assertContains(response, 'href="#catalog-results"')
