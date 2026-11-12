from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Message, Response


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class ProfileMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.anna = users.create_user(username="anna", first_name="Анна")
        cls.misha = users.create_user(username="misha", first_name="Миша")
        cls.stranger = users.create_user(username="stranger")

    def test_profile_messages_reach_existing_inbox_and_share_one_thread(self):
        self.client.force_login(self.anna)
        profile = reverse("ads:user_profile", args=[self.misha.username])
        compose = reverse("ads:profile_message", args=[self.misha.username])
        self.assertContains(self.client.get(profile), compose)
        self.assertContains(self.client.get(compose), "Новое сообщение")
        self.assertEqual(self.client.post(compose, {"text": "  "}).status_code, 400)
        self.assertFalse(Response.objects.exists())
        response = self.client.post(compose, {"text": "Привет! Калькулятор ещё нужен?"})
        thread = Response.objects.get()
        chat = reverse("ads:conversation", args=[thread.pk])
        self.assertRedirects(response, chat)
        self.assertIsNone(thread.ad_id)
        self.assertEqual(thread.participant_ids, (self.anna.pk, self.misha.pk))
        self.assertNotContains(self.client.get(chat), "Принять отклик")

        self.client.force_login(self.misha)
        inbox = self.client.get(reverse("ads:inbox"))
        self.assertContains(inbox, "Калькулятор ещё нужен?")
        self.assertEqual(inbox.context["unread_messages"], 1)
        self.assertRedirects(
            self.client.get(reverse("ads:profile_message", args=[self.anna.username])), chat
        )
        self.assertTrue(Message.objects.get().read_at)
        # Both directions, including a first-message form still open in another tab.
        self.assertRedirects(
            self.client.post(
                reverse("ads:profile_message", args=[self.anna.username]),
                {"text": "Да, до пятницы."},
            ),
            chat,
        )
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(thread.messages.count(), 2)

    def test_direct_chat_only_allows_participants_and_keeps_listing_actions_separate(self):
        compose = reverse("ads:profile_message", args=[self.misha.username])
        self.assertEqual(self.client.get(compose).status_code, 302)
        self.client.force_login(self.anna)
        self.assertEqual(
            self.client.get(reverse("ads:profile_message", args=[self.anna.username])).status_code,
            404,
        )
        self.client.post(compose, {"text": "Только для Миши"})
        thread = Response.objects.get()
        chat = reverse("ads:conversation", args=[thread.pk])
        api_list = reverse("api-conversation-list")
        api_messages = reverse("api-conversation-messages", args=[thread.pk])

        api = APIClient()
        api.force_authenticate(self.misha)
        self.assertEqual(api.get(api_list).json()["results"], [])
        self.assertEqual(api.get(api_messages).json()["results"][0]["text"], "Только для Миши")
        self.assertEqual(api.post(api_messages, {"text": "Ответ получил."}).status_code, 201)
        self.assertEqual(
            self.client.post(reverse("ads:accept_response", args=[thread.pk])).status_code, 404
        )

        self.client.force_login(self.stranger)
        api.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(chat).status_code, 404)
        self.assertEqual(self.client.post(chat, {"text": "Чужой ответ"}).status_code, 404)
        self.assertEqual(api.get(api_messages).status_code, 404)
        self.assertNotContains(self.client.get(reverse("ads:inbox_sidebar")), "Только для Миши")
