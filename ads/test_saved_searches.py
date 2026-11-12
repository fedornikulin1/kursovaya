from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Ad, Category, SavedSearch


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class SavedSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("search_owner")
        cls.other = get_user_model().objects.create_user("search_other")
        cls.category = Category.objects.create(name="Электроника")
        cls.cheap = Ad.objects.create(
            title="Калькулятор", author=cls.other, category=cls.category, price=400
        )
        Ad.objects.create(
            title="Калькулятор подороже", author=cls.other, category=cls.category, price=800
        )

    def test_save_reopen_and_delete_preserve_current_filters(self):
        self.client.force_login(self.owner)
        save_url = reverse("ads:save_search")
        catalogue = reverse("ads:ad_list")
        criteria = {
            "category": self.category.pk,
            "ordering": "price",
            "price_max": "500",
            "q": "Калькулятор",
        }
        query = urlencode(criteria)
        active_url = f"{catalogue}?{query}#catalog-results"
        draft_query = urlencode(
            {**criteria, "price_max": "500.00", "page": 2, "next": "//example.org"}
        )

        initial = self.client.get(catalogue, criteria)
        self.assertContains(initial, "Сохранить поиск")
        self.assertRedirects(self.client.post(f"{save_url}?{draft_query}"), active_url)
        self.assertRedirects(self.client.post(f"{save_url}?{query}"), active_url)
        saved = self.owner.saved_searches.get()
        self.assertEqual(saved.query_string, query)
        self.assertContains(self.client.get(catalogue), saved.label)
        self.assertContains(self.client.get(catalogue, criteria), "Этот поиск сохранён")
        self.assertEqual(list(self.client.get(catalogue, criteria).context["ads"]), [self.cheap])

        delete_url = reverse("ads:delete_saved_search", args=[saved.pk])
        self.assertRedirects(self.client.post(f"{delete_url}?{query}"), active_url)
        self.assertFalse(self.owner.saved_searches.exists())

    def test_saved_searches_require_login_csrf_and_ownership(self):
        save_url = reverse("ads:save_search")
        query = urlencode({"q": "Личный поиск"})
        self.assertEqual(self.client.post(f"{save_url}?{query}").status_code, 302)
        self.assertFalse(SavedSearch.objects.exists())

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(f"{save_url}?{query}").status_code, 403)
        self.assertFalse(SavedSearch.objects.exists())

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(f"{save_url}?{query}").status_code, 405)
        self.client.post(f"{save_url}?{query}")
        saved = self.owner.saved_searches.get()
        delete_url = reverse("ads:delete_saved_search", args=[saved.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 405)

        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("ads:ad_list")), saved.label)
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.assertTrue(SavedSearch.objects.filter(pk=saved.pk).exists())

    def test_food_search_stays_in_food_catalogue_when_reopened(self):
        self.client.force_login(self.owner)
        food, _ = Category.objects.get_or_create(name="Продукты")
        snack = Ad.objects.create(
            title="Шоколад", author=self.other, category=food, price=100
        )
        query = urlencode({"food": "1", "price_max": "500"})
        response = self.client.post(f"{reverse('ads:save_search')}?{query}")
        self.assertRedirects(response, f"/?{query}#catalog-results")
        saved = self.owner.saved_searches.get()
        self.assertIn("Продукты", saved.label)
        reopened = self.client.get(f"/?{saved.query_string}")
        self.assertTrue(reopened.context["food_mode"])
        self.assertEqual(list(reopened.context["ads"]), [snack])

    def test_ajax_delete_can_be_undone_only_by_owner(self):
        self.client.force_login(self.owner)
        search = SavedSearch.objects.create(user=self.owner, query_string="price_max=500", label="До 500 ₽")
        deleted = self.client.post(
            reverse("ads:delete_saved_search", args=[search.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(self.owner.saved_searches.exists())
        self.assertNotIn(search.label, deleted.json()["html"])
        token = {"undo_token": deleted.json()["undo_token"]}
        restore_url = reverse("ads:restore_saved_search")

        self.client.force_login(self.other)
        self.assertEqual(self.client.post(restore_url, token).status_code, 403)
        self.client.force_login(self.owner)
        restored = self.client.post(restore_url, token)
        self.assertEqual(restored.status_code, 200)
        self.assertIn(search.label, restored.json()["html"])
        self.assertEqual(self.client.post(restore_url, token).status_code, 200)
        self.assertEqual(self.owner.saved_searches.get().query_string, search.query_string)

    def test_empty_or_invalid_filters_cannot_be_saved(self):
        self.client.force_login(self.owner)
        save_url = reverse("ads:save_search")
        for query in ("", "page=2", "ordering=-date", "price_max=-1", "ordering=unknown"):
            with self.subTest(query=query):
                self.assertRedirects(
                    self.client.post(f"{save_url}?{query}"), reverse("ads:ad_list")
                )
        self.assertFalse(SavedSearch.objects.exists())
