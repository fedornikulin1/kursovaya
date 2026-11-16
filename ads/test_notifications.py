from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from campus.models import CampusMessage

from .models import Ad, Category, Notification, SavedSearch


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.reader = users.create_user("watcher")
        cls.seller = users.create_user("publisher")
        cls.category = Category.objects.create(name="Учебные вещи")

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def listing(self, title, **fields):
        return Ad.objects.create(
            title=title, author=fields.pop("author", self.seller), category=self.category,
            price=fields.pop("price", 700), **fields,
        )

    def test_saved_search_notifies_once_for_a_matching_first_publication(self):
        old = self.listing("Калькулятор старый")
        draft = self.listing("Калькулятор из черновика", status=Ad.Status.DRAFT)
        self.assertIsNone(draft.published_at)
        self.client.force_login(self.reader)
        save_url = reverse("ads:save_search")
        for filters in ({"q": "Калькулятор", "price_max": 800}, {"category": self.category.pk, "price_max": 800}):
            self.client.post(f"{save_url}?{urlencode(filters)}")
        self.assertEqual(SavedSearch.objects.count(), 2)
        self.listing("Калькулятор дорогой", price=1200)
        self.listing("Калькулятор мой", author=self.reader)
        draft.status = Ad.Status.ACTIVE
        draft.save(update_fields=["status"])
        count_url = reverse("ads:notification_count")
        self.assertEqual(self.client.get(count_url).json(), {"unread": 1})
        self.assertEqual(self.client.get(count_url).json(), {"unread": 1})
        notice = Notification.objects.get(user=self.reader)
        self.assertEqual(notice.listing, draft)
        self.assertNotEqual(notice.listing, old)
        inbox = reverse("ads:notifications")
        self.assertContains(self.client.get(inbox), draft.title)
        open_url = reverse("ads:notification_open", args=[notice.pk])
        self.assertEqual(self.client.get(open_url).status_code, 405)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(open_url).status_code, 404)
        self.client.force_login(self.reader)
        self.assertRedirects(self.client.post(open_url), draft.get_absolute_url())
        self.assertEqual(self.client.get(count_url).json(), {"unread": 0})

        recent = self.listing("Калькулятор ещё один")
        self.assertEqual(self.client.get(count_url).json(), {"unread": 1})
        recent.status = Ad.Status.ARCHIVED
        recent.save(update_fields=["status"])
        self.assertNotContains(self.client.get(inbox), recent.title)
        self.assertEqual(self.client.get(count_url).json(), {"unread": 0})

    def test_private_wanted_reply_notifies_only_asker_and_read_all_includes_new_matches(self):
        request = CampusMessage.objects.create(author=self.reader, body="Ищу инженерный калькулятор", kind="wanted")
        self.client.force_login(self.seller)
        reply = self.client.post(reverse("campus:offer_wanted", args=[request.pk]), {"text": "Есть такой"})
        self.assertEqual(reply.status_code, 302)
        self.assertEqual(self.client.get(reverse("ads:notification_count")).json(), {"unread": 0})
        self.client.force_login(self.reader)
        offer = Notification.objects.get(user=self.reader)
        self.assertEqual(offer.get_absolute_url(), reply.url)
        self.assertContains(self.client.get(reverse("ads:notifications")), "На ваш запрос откликнулись")
        SavedSearch.objects.create(user=self.reader, query_string=urlencode({"q": "Калькулятор"}))
        self.listing("Калькулятор рядом")
        self.client.post(reverse("ads:notifications_read_all"))
        self.assertEqual(Notification.objects.filter(user=self.reader, read_at__isnull=False).count(), 2)
