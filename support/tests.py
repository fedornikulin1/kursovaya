import os
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from ads.models import Ad, Category, Notification
from campus.models import CampusMessage

from .models import ContentReport, FAQ, SupportMessage, SupportTicket
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

    def test_content_reports_are_private_idempotent_and_admin_keeps_snapshot_and_decision(self):
        cache.clear()
        self.addCleanup(cache.clear)
        ad = Ad.objects.create(
            author=self.outsider, category=Category.objects.create(name="Учебники"),
            title="Продаю учебник", description="Текст объявления <b>для проверки</b>", price=250,
        )
        item = CampusMessage.objects.create(author=self.outsider, body="Сообщение для проверки")
        listing_url = reverse("support:report_listing", args=[ad.pk])
        message_url = reverse("support:report_chat_message", args=[item.pk])
        self.assertEqual(self.client.get(listing_url).status_code, 302)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(listing_url).status_code, 403)
        self.assertEqual(self.client.get(message_url).status_code, 403)

        self.client.force_login(self.user)
        self.assertContains(self.client.get(ad.get_absolute_url()), listing_url)
        self.assertContains(self.client.get(reverse("campus:chat")), message_url)
        report_data = {"reason": "spam", "text": "Проверьте повторные публикации"}
        first = self.client.post(listing_url, report_data)
        self.assertEqual(self.client.post(listing_url, report_data).url, first.url)
        chat_response = self.client.post(message_url, report_data)
        self.assertEqual(chat_response.status_code, 302)
        self.assertEqual(ContentReport.objects.count(), 2)
        self.assertEqual(SupportTicket.objects.count(), 2)
        report = ContentReport.objects.get(kind="listing")
        self.assertEqual(report.reporter, self.user)
        chat_report = ContentReport.objects.get(kind="chat")
        self.assertIn(f"?around={item.pk}#campus-message-{item.pk}", chat_report.target_url)
        self.assertContains(self.client.get(first.url), "Модерация · Новая")
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(first.url).status_code, 404)

        ad.delete()
        queue = reverse("admin:support_contentreport_changelist")
        change = reverse("admin:support_contentreport_change", args=[report.pk])
        self.client.force_login(self.unprivileged_staff)
        self.assertEqual(self.client.get(queue).status_code, 403)
        self.client.force_login(self.root)
        self.assertContains(self.client.get(queue, {"status__exact": "new"}), report.target_label)
        self.assertContains(self.client.get(change), "Текст объявления &lt;b&gt;для проверки&lt;/b&gt;")
        invalid = self.client.post(change, {"status": "resolved", "moderator_note": ""})
        self.assertContains(invalid, "Укажите, почему вы приняли это решение.")
        self.assertEqual(report.status, ContentReport.Status.NEW)
        self.assertEqual(
            self.client.post(change, {"status": "resolved", "moderator_note": "Публикация удалена"}).status_code,
            302,
        )
        report.refresh_from_db()
        self.assertEqual(report.status, ContentReport.Status.RESOLVED)
        log = LogEntry.objects.get(object_id=str(report.pk), content_type__model="contentreport")
        self.assertEqual(log.user, self.root)
        self.assertIn("Публикация удалена", log.get_change_message())
        self.client.force_login(self.user)
        detail = self.client.get(first.url)
        self.assertContains(detail, "Модерация · Меры приняты")
        self.assertNotContains(detail, "Публикация удалена")
        notice = Notification.objects.get(ticket=report.ticket)
        self.assertEqual(notice.user, self.user)
        self.assertEqual(notice.detail, "Меры приняты")
        self.assertEqual(notice.get_absolute_url(), first.url)

    def test_quick_moderation_checks_permissions_and_records_each_action(self):
        cache.clear()
        self.addCleanup(cache.clear)
        ad = Ad.objects.create(
            author=self.outsider, category=Category.objects.create(name="Книги"),
            title="Учебник", description="Описание", price=250,
        )
        item = CampusMessage.objects.create(author=self.outsider, body="Текст сообщения")
        self.client.force_login(self.user)
        for kind, pk in (("listing", ad.pk), ("chat_message", item.pk)):
            self.client.post(reverse(f"support:report_{kind}", args=[pk]), {"reason": "spam", "text": "Проверить"})
        listing_report = ContentReport.objects.get(kind="listing")
        message_report = ContentReport.objects.get(kind="chat")
        hide_url = reverse("admin:support_contentreport_moderate", args=[listing_report.pk, "hide-listing"])
        remove_url = reverse("admin:support_contentreport_moderate", args=[message_report.pk, "remove-message"])
        block_url = reverse("admin:support_contentreport_moderate", args=[message_report.pk, "block-author"])
        decision_url = reverse("admin:support_contentreport_change", args=[listing_report.pk])
        permission = Permission.objects.get(content_type__app_label="support", codename="change_contentreport")
        self.staff.user_permissions.add(permission)
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(decision_url), "Скрыть объявление")
        self.assertEqual(self.client.post(hide_url, {"reason": "Проверено"}).status_code, 403)
        self.assertEqual(self.client.post(remove_url, {"reason": "Проверено"}).status_code, 403)
        self.assertEqual(self.client.post(block_url, {"reason": "Проверено"}).status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label="ads", codename="change_ad"))
        self.assertContains(self.client.get(decision_url), "Скрыть объявление")
        self.assertContains(self.client.get(hide_url), "Причина решения")
        self.assertEqual(Ad.objects.get(pk=ad.pk).status, Ad.Status.ACTIVE)
        self.assertEqual(self.client.post(hide_url, {"reason": ""}).status_code, 200)
        self.assertRedirects(self.client.post(hide_url, {"reason": "Подтверждённый спам"}), decision_url)
        ad.refresh_from_db()
        self.assertTrue(ad.moderation_hidden)
        self.assertEqual(ad.status, Ad.Status.ARCHIVED)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(ad.get_absolute_url()).status_code, 404)
        self.client.force_login(self.outsider)
        self.assertContains(self.client.get(ad.get_absolute_url()), "Объявление скрыто модератором")
        api = APIClient()
        api.force_authenticate(self.outsider)
        self.assertEqual(api.patch(reverse("api-ad-detail", args=[ad.pk]), {"status": "active"}).status_code, 400)
        self.client.force_login(self.root)
        self.assertEqual(self.client.post(remove_url, {"reason": "Повторный спам"}).status_code, 302)
        self.assertFalse(CampusMessage.objects.filter(pk=item.pk).exists())
        self.assertEqual(self.client.post(block_url, {"reason": "Продолжил рассылку"}).status_code, 302)
        self.outsider.refresh_from_db()
        self.assertFalse(self.outsider.is_active)
        self.assertEqual(Notification.objects.filter(user=self.user, kind=Notification.Kind.REPORT).count(), 2)
        self.assertEqual(
            list(LogEntry.objects.filter(content_type__model="contentreport", object_id=str(message_report.pk))
                 .order_by("pk").values_list("change_message", flat=True)),
            [f"Сообщение удалено по жалобе № {message_report.pk}. Причина: Повторный спам",
             f"Автор заблокирован по жалобе № {message_report.pk}. Причина: Продолжил рассылку"],
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

    @override_settings(SUPPORT_AI_API_KEY="mock-key", SUPPORT_AI_MODEL_URI="gpt://mock-folder/yandexgpt-lite/latest")
    def test_assistant_uses_public_faq_and_offers_human_fallback(self):
        cache.clear()
        self.addCleanup(cache.clear)
        FAQ.objects.create(topic="other", question="Скрытый черновик", answer="Не отправлять", is_published=False)
        self.make_ticket(text="Секретный текст обращения")
        url = reverse("support:ask")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("support:help")), "Спросить ИИ-помощника")
        raw = json.dumps({"result": {"alternatives": [{"message": {"text": "Откройте объявление."}}]}}).encode()
        with patch("support.assistant.urlopen", return_value=BytesIO(raw)) as provider:
            response = self.client.post(url, {"question": "Как написать продавцу?"})
        self.assertContains(response, "Откройте объявление.")
        body = json.loads(provider.call_args.args[0].data)
        self.assertIn("Как написать продавцу?", body["messages"][1]["text"])
        self.assertNotIn("Скрытый черновик", body["messages"][0]["text"])
        self.assertNotIn("Секретный текст обращения", body["messages"][0]["text"])
        with patch("support.assistant.urlopen", side_effect=URLError("timeout")):
            self.assertContains(
                self.client.post(url, {"question": "Как написать продавцу?"}),
                "Вопрос можно отправить сотруднику.",
            )

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

    def test_profile_report_reaches_support_and_is_private(self):
        report_url = reverse("support:report_profile", args=[self.outsider.username])
        self.client.force_login(self.user)
        self.assertContains(self.client.get(report_url), "Причина жалобы")
        response = self.client.post(
            report_url,
            {
                "reason": "prohibited_goods",
                "text": "Ссылка на объявление для проверки",
                "user": self.staff.pk,
                "target": self.root.pk,
            },
        )
        ticket = SupportTicket.objects.get()
        self.assertRedirects(response, ticket.get_absolute_url())
        self.assertEqual(ticket.user, self.user)
        self.assertEqual(ticket.topic, SupportTicket.Topic.SAFETY)
        self.assertIn(f"@{self.outsider.username} (№ {self.outsider.pk})", ticket.messages.get().text)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(ticket.get_absolute_url()).status_code, 404)
        self.client.force_login(self.staff)
        admin_url = reverse("admin:support_supportticket_change", args=[ticket.pk])
        self.assertContains(self.client.get(admin_url), "Причина: Запрещённые товары")

    def test_profile_report_rejects_anonymous_self_and_forged_reason(self):
        client = Client(enforce_csrf_checks=True)
        report_url = reverse("support:report_profile", args=[self.outsider.username])
        self.assertEqual(client.get(report_url).status_code, 302)
        client.force_login(self.user)
        self.assertEqual(client.post(report_url, {"reason": "spam", "text": "Повтор"}).status_code, 403)
        self_url = reverse("support:report_profile", args=[self.user.username])
        self.assertEqual(client.get(self_url).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.post(report_url, {"reason": "admin", "text": "Подмена"})
        self.assertContains(response, "Причина жалобы")
        self.assertFalse(SupportTicket.objects.exists())

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
