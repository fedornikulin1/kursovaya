from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from ads.models import Ad, Category, Message

from .models import CampusMessage


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class CampusChatTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.asker = users.create_user(username="campus_asker", first_name="Анна")
        cls.responder = users.create_user(username="campus_responder", first_name="Миша")

    def test_chat_and_feed_require_login_and_post_requires_csrf(self):
        chat = reverse("campus:chat")
        feed = reverse("campus:chat_feed")
        self.assertRedirects(self.client.get(chat), f"{reverse('login')}?next={chat}")
        self.assertEqual(self.client.get(feed).status_code, 302)
        self.assertEqual(self.client.post(chat, {"body": "Вопрос"}).status_code, 302)

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.asker)
        self.assertEqual(client.post(chat, {"body": "Вопрос"}).status_code, 403)
        self.assertFalse(CampusMessage.objects.exists())

    def test_two_users_can_ask_and_reply_and_feed_escapes_markup(self):
        chat = reverse("campus:chat")
        feed = reverse("campus:chat_feed")
        self.client.force_login(self.asker)
        self.assertRedirects(
            self.client.post(chat, {"kind": "wanted", "body": "У кого есть калькулятор <b>?"}),
            chat,
        )
        question = CampusMessage.objects.get(author=self.asker)
        self.assertEqual(question.kind, CampusMessage.Kind.WANTED)

        self.client.force_login(self.responder)
        page = self.client.get(chat, {"reply": question.pk})
        self.assertEqual(page.context["chat_reply"], question)
        self.assertContains(page, "калькулятор &lt;b&gt;?")
        self.assertRedirects(
            self.client.post(chat, {"body": "Есть, могу одолжить", "reply_to": question.pk}),
            chat,
        )
        answer = CampusMessage.objects.get(author=self.responder)
        self.assertEqual(answer.reply_to, question)

        self.client.force_login(self.asker)
        response = self.client.get(feed, {"after": question.pk})
        payload = response.json()
        self.assertEqual(payload["latest_id"], answer.pk)
        self.assertIn("Есть, могу одолжить", payload["html"])
        self.assertIn("калькулятор &lt;b&gt;?", payload["html"])
        self.assertNotIn("калькулятор <b>?", payload["html"])
        self.assertEqual(self.client.get(feed, {"after": answer.pk}).json()["html"], "")

    def test_invalid_messages_are_not_saved(self):
        self.client.force_login(self.asker)
        chat = reverse("campus:chat")
        for data in (
            {"body": "  "},
            {"body": "x" * 1001},
            {"body": "Вопрос", "kind": "invalid"},
            {"body": "Вопрос", "reply_to": 123456},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(chat, data).status_code, 400)
        self.assertFalse(CampusMessage.objects.exists())

    def test_json_post_returns_reply_without_redirect_and_keeps_validation(self):
        self.client.force_login(self.responder)
        original = CampusMessage.objects.create(author=self.asker, body="У кого есть линейка?")
        chat = reverse("campus:chat")
        invalid = self.client.post(chat, {"body": "  "}, HTTP_ACCEPT="application/json")
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("body", invalid.json()["errors"])
        response = self.client.post(
            chat, {"body": "Есть, могу одолжить", "reply_to": original.pk},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("Есть, могу одолжить", response.json()["html"])
        self.assertIn(f"?around={original.pk}#campus-message-{original.pk}", response.json()["html"])
        self.assertEqual(CampusMessage.objects.filter(author=self.responder).count(), 1)

    def test_public_chat_rejects_abuse_and_prohibited_transactions(self):
        self.client.force_login(self.asker)
        chat = reverse("campus:chat")
        for body, kind, reason in (
            ("Что за хyйня?", "general", "ненормативную лексику"),
            ("х.у.й", "general", "ненормативную лексику"),
            ("Продам мефедрон", "general", "нельзя предлагать или искать"),
            ("Могу достать поддельный паспорт", "general", "нельзя предлагать или искать"),
            ("Боеприпасы", "wanted", "нельзя предлагать или искать"),
        ):
            with self.subTest(body=body):
                response = self.client.post(chat, {"body": body, "kind": kind})
                self.assertContains(response, reason, status_code=400)
        self.assertFalse(CampusMessage.objects.exists())

    def test_public_chat_accepts_ordinary_goods_and_discussion_of_rules(self):
        self.client.force_login(self.asker)
        chat = reverse("campus:chat")
        for body in (
            "Продам клеевой пистолет за 300 рублей.",
            "Куплю патроны для ламп.",
            "Ищу учебник по истории оружия.",
            "Продажа наркотиков запрещена. Куда отправить жалобу?",
            "Ищу героиню для роли в студенческой постановке.",
        ):
            with self.subTest(body=body):
                self.assertRedirects(
                    self.client.post(chat, {"body": body, "kind": "general"}),
                    chat,
                    fetch_redirect_response=False,
                )
        self.assertEqual(CampusMessage.objects.count(), 5)

    def test_feed_is_bounded_and_older_messages_remain_reachable(self):
        entries = CampusMessage.objects.bulk_create(
            [CampusMessage(author=self.asker, body=f"Вопрос {i}") for i in range(51)]
        )
        self.client.force_login(self.responder)
        chat = reverse("campus:chat")
        page = self.client.get(chat)
        self.assertEqual(page.context["chat_older_id"], entries[1].pk)
        archive = self.client.get(chat, {"before": entries[1].pk})
        self.assertTrue(archive.context["chat_is_archive"])
        self.assertEqual(archive.context["chat_messages"], entries[:1])
        quoted = self.client.get(chat, {"around": entries[0].pk})
        self.assertTrue(quoted.context["chat_is_archive"])
        self.assertContains(quoted, f'id="campus-message-{entries[0].pk}"')
        feed = self.client.get(reverse("campus:chat_feed"), {"after": 0}).json()
        self.assertTrue(feed["has_more"])
        self.assertEqual(feed["latest_id"], entries[-2].pk)

    def test_only_author_can_close_request_and_active_feed_reconciles_it(self):
        wanted = CampusMessage.objects.create(author=self.asker, body="Ищу учебник", kind="wanted")
        spare = CampusMessage.objects.create(author=self.asker, body="Ищу рюкзак", kind="wanted")
        chat = reverse("campus:chat")
        close = reverse("campus:close_wanted", args=[wanted.pk])
        self.client.force_login(self.responder)
        self.assertContains(self.client.get(chat, {"view": "wanted"}), "У меня есть")
        self.assertEqual(self.client.post(close, {"status": "found"}).status_code, 404)
        self.client.force_login(self.asker)
        self.assertEqual(self.client.get(close).status_code, 405)
        self.assertRedirects(self.client.post(close, {"status": "found", "view": "wanted"}), f"{chat}?view=wanted")
        self.client.post(close, {"status": "cancelled"})
        wanted.refresh_from_db()
        self.assertEqual(wanted.wanted_status, CampusMessage.WantedStatus.FOUND)
        self.client.post(reverse("campus:close_wanted", args=[spare.pk]), {"status": "cancelled"})
        page = self.client.get(chat)
        self.assertContains(page, "Нашёл")
        self.assertContains(page, "Уже не нужно")
        self.assertNotContains(self.client.get(chat, {"view": "wanted"}), wanted.body)
        feed = reverse("campus:chat_feed")
        response = self.client.get(feed, {"view": "wanted", "watch": f"{wanted.pk},{spare.pk}"}).json()
        self.assertEqual(set(response["removed"]), {str(wanted.pk), str(spare.pk)})
        response = self.client.get(feed, {"after": spare.pk, "watch": wanted.pk}).json()
        self.assertEqual(response["closed_requests"], {str(wanted.pk): "Нашёл"})

    def test_private_offer_accepts_only_own_active_listing_and_supports_text_without_it(self):
        wanted = CampusMessage.objects.create(author=self.asker, body="Ищу линейку", kind="wanted")
        offer_url = reverse("campus:offer_wanted", args=[wanted.pk])
        category = Category.objects.create(name="Канцелярия")
        own = Ad.objects.create(author=self.responder, category=category, title="Линейка", price=200)
        foreign = Ad.objects.create(author=self.asker, category=category, title="Чужой товар", price=300)
        self.client.force_login(self.responder)
        page = self.client.get(offer_url)
        self.assertContains(page, own.title)
        self.assertNotContains(page, foreign.title)
        self.client.post(offer_url, {"text": "Есть линейка", "listing": foreign.pk})
        self.assertFalse(Message.objects.exists())
        response = self.client.post(offer_url, {"text": "Есть линейка", "listing": own.pk})
        message = Message.objects.get()
        self.assertRedirects(response, reverse("ads:conversation", args=[message.response_id]))
        self.assertEqual(message.offered_ad, own)
        self.assertIn(wanted.body, message.text)
        self.assertEqual(CampusMessage.objects.count(), 1)
        self.assertEqual(self.client.post(offer_url, {"text": "Можно забрать завтра"}).status_code, 302)
        self.assertIsNone(Message.objects.get(text__endswith="Можно забрать завтра").offered_ad)
        self.client.force_login(self.asker)
        self.assertContains(self.client.get(reverse("ads:conversation", args=[message.response_id])), own.get_absolute_url())
        api = APIClient()
        api.force_authenticate(self.asker)
        sent = api.get(reverse("api-conversation-messages", args=[message.response_id]), {"after": 0})
        self.assertEqual(sent.data["results"][0]["offered_ad"]["url"], own.get_absolute_url())
        self.client.post(reverse("campus:close_wanted", args=[wanted.pk]), {"status": "found"})
        self.client.force_login(self.responder)
        self.assertEqual(self.client.post(offer_url, {"text": "Есть"}).status_code, 404)
        self.assertEqual(Message.objects.count(), 2)


class CampusChatDemoTests(TestCase):
    @override_settings(DEBUG=True)
    def test_demo_conversation_is_additive_and_idempotent(self):
        users = get_user_model().objects
        for name in ("demo_anna", "demo_dmitry", "demo_alina", "demo_mikhail"):
            users.create_user(username=name, email=f"{name}@demo.example")
        existing = CampusMessage.objects.create(author=users.get(username="demo_anna"), body="Привет!")

        call_command("seed_campus_chat_demo", stdout=StringIO())
        call_command("seed_campus_chat_demo", stdout=StringIO())

        demo = CampusMessage.objects.filter(body__startswith="Демо · ")
        self.assertEqual(demo.count(), 5)
        self.assertEqual(demo.values("author_id").distinct().count(), 4)
        self.assertEqual(demo.filter(reply_to__in=demo).count(), 3)
        self.assertTrue(CampusMessage.objects.filter(pk=existing.pk, body="Привет!").exists())

    @override_settings(DEBUG=True)
    def test_demo_command_never_posts_from_non_demo_accounts(self):
        users = get_user_model().objects
        for name in ("demo_anna", "demo_dmitry", "demo_alina", "demo_mikhail"):
            users.create_user(username=name, email=f"{name}@demo.example")
        users.filter(username="demo_anna").update(email="real@example.org")

        with self.assertRaises(CommandError):
            call_command("seed_campus_chat_demo", stdout=StringIO())
        self.assertFalse(CampusMessage.objects.exists())
