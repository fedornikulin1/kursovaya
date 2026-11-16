from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from campus.models import CampusMessage
from .authentication import APPROVED_STUDENTS
from .models import Ad, Category, Message, Response


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.student = users.create_user(username="student", password="private-demo-pass")
        cls.peer = users.create_user(username="peer", password="private-demo-pass")
        cls.admin = users.create_superuser(username="operator", password="operator-demo-pass")
        cls.category = Category.objects.create(name="Проверка каталога")

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(STUDENT_ACCESS_ONLY=True)
    def test_closed_enrolment_rejects_local_registration_existing_sessions_and_tokens(self):
        self.client.force_login(self.student, backend="ads.authentication.RegistrationBackend")
        self.assertEqual(self.client.get(reverse("campus:chat")).status_code, 302)
        self.assertRedirects(self.client.get(reverse("ads:register")), reverse("login"))
        self.assertEqual(self.client.post("/api/v1/auth/register/", {}).status_code, 403)
        credentials = {"username": self.student.username, "password": "private-demo-pass"}
        api = APIClient()
        self.assertEqual(api.post("/api/v1/auth/token/", credentials).status_code, 401)
        token = RefreshToken.for_user(self.student)
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.assertEqual(api.get("/api/v1/me/").status_code, 401)
        self.assertEqual(api.post("/api/v1/auth/token/refresh/", {"refresh": str(token)}).status_code, 401)

        self.student.groups.add(Group.objects.create(name=APPROVED_STUDENTS))
        self.assertRedirects(self.client.post(reverse("login"), credentials), reverse("ads:ad_list"))
        self.assertEqual(self.client.get(reverse("campus:chat")).status_code, 200)
        self.assertEqual(api.get("/api/v1/me/").status_code, 200)

    @override_settings(STUDENT_ACCESS_ONLY=True)
    def test_catalogue_counts_match_visible_ads(self):
        approved = Group.objects.create(name=APPROVED_STUDENTS)
        self.student.groups.add(approved)
        blocked = get_user_model().objects.create_user(username="blocked", is_active=False)
        blocked.groups.add(approved)
        for author, title, status in (
            (self.student, "Настольная лампа", Ad.Status.ACTIVE),
            (self.student, "Черновик", Ad.Status.DRAFT),
            (self.peer, "Без подтверждения", Ad.Status.ACTIVE),
            (blocked, "Скрыто после блокировки", Ad.Status.ACTIVE),
        ):
            Ad.objects.create(author=author, category=self.category, title=title, price=100, status=status)

        response = self.client.get(reverse("ads:ad_list"), {"category": self.category.pk})
        category = next(item for item in response.context["categories"] if item.pk == self.category.pk)
        self.assertEqual(category.active_count, 1)
        self.assertEqual(response.context["total_ads"], 1)
        self.assertEqual([ad.title for ad in response.context["ads"]], ["Настольная лампа"])

    def test_chat_rate_and_size_limits(self):
        self.client.force_login(self.student)
        url = reverse("campus:chat")
        large = self.client.post(url, {"body": "x" * 20000}, HTTP_ACCEPT="application/json")
        self.assertEqual(large.status_code, 413)
        with patch("config.abuse.time", return_value=120):
            for _ in range(12):
                self.assertEqual(self.client.post(url, {"body": "Ищу лампу"}).status_code, 302)
            response = self.client.post(url, {"body": "Ищу лампу"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(CampusMessage.objects.filter(author=self.student).count(), 12)

    def test_listing_moderation_and_shared_creation_quota(self):
        url = reverse("ads:ad_create")
        api = APIClient()
        token = RefreshToken.for_user(self.student)
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.client.force_login(self.student)
        payload = {
            "title": "Продам вейп", "category": self.category.pk, "description": "Описание",
            "price": 100, "price_type": "fixed", "condition": "new", "kind": "sell", "status": "active",
        }
        with patch("config.abuse.time", return_value=3600):
            self.assertEqual(self.client.post(url, payload, HTTP_ACCEPT="application/json").status_code, 400)
            self.assertEqual(api.post("/api/v1/ads/", payload).status_code, 400)
            payload["title"] = "Настольная лампа"
            for _ in range(6):
                self.assertEqual(api.post("/api/v1/ads/", payload).status_code, 201)
            self.assertEqual(self.client.post(url, payload).status_code, 429)
        self.assertEqual(Ad.objects.filter(author=self.student).count(), 6)

    def test_admin_history_requires_reason_and_block_hides_listings(self):
        ad = Ad.objects.create(
            author=self.student, category=self.category, title="Настольная лампа", price=100,
        )
        thread = Response.objects.create(ad=ad, user=self.peer)
        Message.objects.create(response=thread, sender=self.peer, text="Приватный текст для теста")
        dialog = reverse("admin:student_dialogues", args=[self.student.pk])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(dialog).status_code, 302)
        self.peer.is_staff = True
        self.peer.save(update_fields=["is_staff"])
        self.peer.user_permissions.add(Permission.objects.get(
            content_type__app_label="auth", codename="view_user"
        ))
        self.client.force_login(self.peer)
        self.assertEqual(self.client.get(dialog).status_code, 403)
        self.client.force_login(self.admin)
        account_url = reverse("admin:auth_user_change", args=[self.student.pk])
        self.assertContains(self.client.get(account_url), "Чат кампуса")
        for target in ("admin:ads_ad_changelist", "admin:campus_campusmessage_changelist"):
            self.assertEqual(self.client.get(
                reverse(target), {"author__id__exact": self.student.pk}
            ).status_code, 200)
        self.assertNotContains(self.client.get(dialog), "Приватный текст для теста")
        self.assertNotContains(self.client.post(dialog, {"thread": thread.pk}), "Приватный текст для теста")
        self.assertContains(self.client.post(dialog, {
            "thread": thread.pk, "reason": "Проверка жалобы",
        }), "Приватный текст для теста")
        self.assertTrue(LogEntry.objects.filter(user=self.admin, change_message__contains="Проверка жалобы").exists())

        refresh = RefreshToken.for_user(self.student)
        self.assertEqual(self.client.post(reverse("admin:auth_user_changelist"), {
            "action": "block_accounts", "_selected_action": [self.student.pk],
        }).status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())
        self.assertEqual(Client().get(ad.get_absolute_url()).status_code, 404)
        delete_url = reverse("admin:auth_user_delete", args=[self.student.pk])
        self.assertContains(self.client.get(delete_url), "student")
        csrf_token = self.client.cookies["csrftoken"].value
        self.assertEqual(self.client.post(delete_url, {
            "post": "yes", "csrfmiddlewaretoken": csrf_token,
        }).status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.student.pk).exists())
