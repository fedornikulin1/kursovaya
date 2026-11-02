import os
from pathlib import Path

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from .models import FAQ, SupportMessage, SupportTicket
from .selectors import tickets_for
from .services import create_ticket, reply_ticket, set_status


@override_settings(
    AXES_ENABLED=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SupportTests(TestCase):
    def export_preview(self, response, name):
        """Optional disposable HTML fixture with test-only data for visual review."""
        if os.getenv("SUPPORT_UI_PREVIEW") == "1":
            target = Path("ads/static/ads") / f"_support-{name}-preview.html"
            target.write_text(response.content.decode(), encoding="utf-8")

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user("student", password="Test-password-2026!")
        cls.outsider = User.objects.create_user("outsider", password="Test-password-2026!")
        cls.staff = User.objects.create_user(
            "operator", password="Test-password-2026!", is_staff=True
        )
        cls.staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="support",
                codename__in=["view_supportticket", "change_supportticket", "view_faq"],
            )
        )
        cls.unprivileged_staff = User.objects.create_user("staff_without_role", is_staff=True)
        cls.root = User.objects.create_superuser("root", password="Test-password-2026!")

    def make_ticket(self, **kwargs):
        return create_ticket(
            user=kwargs.pop("user", self.user),
            subject="Не загружается фото",
            topic="listing",
            text=kwargs.pop("text", "Ошибка при загрузке"),
            **kwargs,
        )

    def test_public_faq_hides_unpublished_answers(self):
        FAQ.objects.create(topic="other", question="Опубликованный вопрос", answer="Открытый ответ")
        FAQ.objects.create(
            topic="other", question="Черновик", answer="Скрытый ответ", is_published=False
        )
        response = self.client.get("/help/")
        self.assertContains(response, "Открытый ответ")
        self.assertNotContains(response, "Скрытый ответ")
        self.assertEqual(self.client.get("/help/tickets/").status_code, 302)

    def test_html_creation_validation_and_sender_cannot_be_forged(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/help/tickets/new/",
            {
                "topic": "listing",
                "subject": "Моя тема",
                "text": "Мой вопрос",
                "user": self.outsider.pk,
                "status": "closed",
            },
        )
        ticket = SupportTicket.objects.get(subject="Моя тема")
        self.assertRedirects(response, ticket.get_absolute_url())
        self.assertEqual(ticket.user, self.user)
        self.assertEqual(ticket.status, "open")
        self.assertFalse(ticket.messages.get().from_staff)
        invalid = self.client.post(
            "/help/tickets/new/", {"topic": "listing", "subject": "Тема", "text": " "}
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(SupportTicket.objects.count(), 1)

    def test_private_pages_and_api_do_not_expose_other_tickets(self):
        ticket = self.make_ticket(text="Секретный вопрос")
        self.client.force_login(self.outsider)
        api = APIClient()
        api.force_authenticate(self.outsider)
        for path in [
            ticket.get_absolute_url(),
            f"/api/v1/support/tickets/{ticket.pk}/",
            f"/api/v1/support/tickets/{ticket.pk}/messages/",
        ]:
            self.assertEqual(
                (api if path.startswith("/api") else self.client).get(path).status_code, 404
            )
        self.assertNotContains(self.client.get("/help/tickets/"), "Секретный вопрос")
        self.assertEqual(api.get("/api/v1/support/tickets/").data["count"], 0)
        self.assertEqual(
            self.client.post(f"/help/tickets/{ticket.pk}/status/", {"action": "close"}).status_code,
            404,
        )

    def test_shared_service_requires_owner_or_authorized_operator(self):
        ticket = self.make_ticket()
        for actor, staff in [
            (self.outsider, False),
            (self.user, True),
            (self.unprivileged_staff, True),
            (self.staff, False),
        ]:
            with self.subTest(actor=actor, staff=staff), self.assertRaises(PermissionDenied):
                reply_ticket(ticket=ticket, actor=actor, text="Подмена", staff=staff)
        self.assertEqual(ticket.messages.count(), 1)

    def test_reply_read_close_and_reopen_lifecycle(self):
        ticket = self.make_ticket()
        reply = reply_ticket(ticket=ticket, actor=self.staff, text="Используйте JPEG", staff=True)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "answered")
        self.assertEqual(tickets_for(self.user).get(pk=ticket.pk).unread_answers, 1)
        self.client.force_login(self.user)
        response = self.client.get(ticket.get_absolute_url())
        self.assertContains(response, "Используйте JPEG")
        reply.refresh_from_db()
        self.assertIsNotNone(reply.read_at)
        self.assertIn("no-store", response["Cache-Control"])
        self.client.post(ticket.get_absolute_url(), {"text": "Всё ещё ошибка"})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "open")
        self.client.post(f"/help/tickets/{ticket.pk}/status/", {"action": "close"})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "closed")
        with self.assertRaises(ValidationError):
            reply_ticket(ticket=ticket, actor=self.user, text="Новый текст")
        self.client.post(f"/help/tickets/{ticket.pk}/status/", {"action": "reopen"})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "open")
        self.assertEqual(ticket.messages.count(), 3)

    def test_api_reuses_services_and_prevents_staff_impersonation(self):
        api = APIClient()
        api.force_authenticate(self.user)
        response = api.post(
            "/api/v1/support/tickets/",
            {
                "subject": "API вопрос",
                "topic": "other",
                "text": "Помогите",
                "user": self.outsider.pk,
            },
        )
        self.assertEqual(response.status_code, 201)
        pk = response.data["id"]
        response = api.post(
            f"/api/v1/support/tickets/{pk}/messages/", {"text": "Дополнение", "from_staff": True}
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["from_staff"])
        self.assertEqual(api.get(f"/api/v1/support/tickets/{pk}/messages/").data["count"], 2)
        self.assertEqual(api.post(f"/api/v1/support/tickets/{pk}/close/").data["status"], "closed")
        self.assertEqual(
            api.post(f"/api/v1/support/tickets/{pk}/messages/", {"text": "Закрыто"}).status_code,
            400,
        )
        self.assertEqual(api.post(f"/api/v1/support/tickets/{pk}/reopen/").data["status"], "open")
        reply_ticket(
            ticket=SupportTicket.objects.get(pk=pk), actor=self.staff, text="Ответ", staff=True
        )
        self.assertEqual(api.post(f"/api/v1/support/tickets/{pk}/read/").status_code, 204)
        self.assertFalse(
            SupportMessage.objects.filter(
                ticket_id=pk, from_staff=True, read_at__isnull=True
            ).exists()
        )

    def test_hourly_limit_and_invalid_first_message_are_atomic(self):
        with self.assertRaises(ValidationError):
            self.make_ticket(text=" " * 4)
        self.assertFalse(SupportTicket.objects.exists())
        for _ in range(5):
            self.make_ticket()
        with self.assertRaises(ValidationError):
            self.make_ticket()
        self.assertEqual(SupportTicket.objects.count(), 5)

    def test_csrf_and_state_changes_require_post(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post("/help/tickets/new/", {"subject": "Атака"}).status_code, 403)
        ticket = self.make_ticket()
        self.assertEqual(client.get(f"/help/tickets/{ticket.pk}/status/").status_code, 405)
        self.assertEqual(self.client.get("/api/v1/support/tickets/").status_code, 401)

    def test_staff_admin_reply_is_logged_and_escapes_message_html(self):
        ticket = self.make_ticket(text="<script>alert('unsafe')</script>")
        self.client.force_login(self.staff)
        response = self.client.get(f"/admin/support/supportticket/{ticket.pk}/change/")
        self.export_preview(response, "ticket")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert('unsafe')</script>")
        response = self.client.post(
            f"/admin/support/supportticket/{ticket.pk}/change/",
            {"reply_text": "Спасибо, проверим", "_save": "Сохранить"},
        )
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "answered")
        self.assertTrue(
            ticket.messages.filter(
                from_staff=True, text="Спасибо, проверим", sender=self.staff
            ).exists()
        )
        self.assertTrue(LogEntry.objects.filter(user=self.staff, object_id=str(ticket.pk)).exists())
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 403)

    def test_dashboard_permissions_and_marketplace_privacy(self):
        self.make_ticket()
        self.client.force_login(self.staff)
        response = self.client.get("/admin/")
        self.assertContains(response, "Ждут ответа")
        self.assertNotContains(response, "Активных объявлений")
        self.client.force_login(self.root)
        response = self.client.get("/admin/")
        self.export_preview(response, "dashboard")
        self.assertContains(response, "Активных объявлений")
        self.assertEqual(self.client.get("/admin/ads/message/").status_code, 404)

    def test_closed_admin_reply_requires_explicit_reopen(self):
        ticket = self.make_ticket()
        set_status(ticket=ticket, actor=self.staff, closed=True, staff=True)
        self.client.force_login(self.staff)
        response = self.client.post(
            f"/admin/support/supportticket/{ticket.pk}/change/",
            {"reply_text": "Ответ", "_save": "Сохранить"},
        )
        self.assertContains(response, "Сначала откройте")
        self.assertEqual(ticket.messages.count(), 1)

    def test_admin_marketplace_and_user_management_still_render(self):
        from ads.models import Ad, Category

        category = Category.objects.create(name="Учебники")
        Ad.objects.create(
            author=self.user,
            category=category,
            title="Учебники для первого курса",
            description="Демонстрационная публикация",
            price=650,
        )
        self.client.force_login(self.root)
        for path in [
            "/admin/ads/ad/",
            "/admin/ads/ad/add/",
            "/admin/auth/user/",
            f"/admin/auth/user/{self.user.pk}/change/",
            "/admin/support/faq/",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                if path == "/admin/ads/ad/":
                    self.export_preview(response, "listings")
                if path == "/admin/ads/ad/add/":
                    self.export_preview(response, "listing-form")
