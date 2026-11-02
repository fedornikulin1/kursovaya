"""Integration tests focus on permissions, privacy and the shared web/API rules."""

import tempfile
from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Ad, Category, Favorite, Message, Response, Review
from .services import create_review, profile_for, save_ad, start_conversation

User = get_user_model()


@override_settings(
    AXES_ENABLED=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class MarketplaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user(
            "seller", "seller@example.org", "Strong-password-471!"
        )
        cls.buyer = User.objects.create_user("buyer", "buyer@example.org", "Strong-password-471!")
        cls.outsider = User.objects.create_user("outsider", password="Strong-password-471!")
        cls.category = Category.objects.create(name="Учебники", icon="book")
        cls.ad = Ad.objects.create(
            title="Математический анализ",
            description="Учебник и конспекты",
            price=450,
            category=cls.category,
            author=cls.seller,
        )

    def setUp(self):
        self.api = APIClient()

    def authenticate(self, user):
        self.client.force_login(user)
        self.api.force_authenticate(user)

    def test_public_pages_render_without_authentication(self):
        for url in [
            "/",
            self.ad.get_absolute_url(),
            "/accounts/login/",
            "/register/",
            "/accounts/password_reset/",
            "/user/seller/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_account_pages_render(self):
        self.authenticate(self.seller)
        for url in [
            "/my-ads/",
            "/favorites/",
            "/messages/",
            "/profile/edit/",
            "/ad/create/",
            f"/ad/{self.ad.pk}/update/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_guest_cannot_post_response(self):
        response = self.client.post(f"/ad/{self.ad.pk}/contact/", {"text": "Здравствуйте"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Response.objects.count(), 0)
        self.assertEqual(
            self.client.post(self.ad.get_absolute_url(), {"text": "attack"}).status_code, 405
        )

    def test_get_does_not_mutate_favorites_or_acceptance(self):
        self.authenticate(self.buyer)
        self.assertEqual(self.client.get(f"/ad/{self.ad.pk}/favorite/").status_code, 405)
        self.assertFalse(Favorite.objects.exists())
        thread = start_conversation(ad=self.ad, user=self.buyer, text="Здравствуйте")
        self.authenticate(self.seller)
        self.assertEqual(self.client.get(f"/response/{thread.pk}/accept/").status_code, 405)
        thread.refresh_from_db()
        self.assertFalse(thread.is_accepted)

    def test_csrf_required_for_web_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.buyer)
        self.assertEqual(client.post(f"/ad/{self.ad.pk}/favorite/").status_code, 403)

    def test_only_owner_can_edit_or_delete(self):
        self.authenticate(self.buyer)
        self.assertEqual(self.client.get(f"/ad/{self.ad.pk}/update/").status_code, 404)
        self.assertEqual(self.client.post(f"/ad/{self.ad.pk}/delete/").status_code, 404)
        self.assertEqual(
            self.api.patch(f"/api/v1/ads/{self.ad.pk}/", {"title": "Hacked"}).status_code, 403
        )
        self.assertEqual(self.api.delete(f"/api/v1/ads/{self.ad.pk}/").status_code, 403)

    def test_draft_and_closed_ad_visibility(self):
        self.ad.status = "draft"
        self.ad.save()
        self.assertEqual(self.client.get(self.ad.get_absolute_url()).status_code, 404)
        self.assertEqual(self.api.get(f"/api/v1/ads/{self.ad.pk}/").status_code, 404)
        self.assertEqual(self.api.get("/api/v1/ads/").data["count"], 0)
        self.authenticate(self.seller)
        self.assertEqual(self.client.get(self.ad.get_absolute_url()).status_code, 200)
        self.assertEqual(self.api.get("/api/v1/ads/mine/").data["count"], 1)

    def test_phone_is_private_and_opt_in(self):
        profile = profile_for(self.seller)
        profile.phone = "+79991234567"
        profile.save()
        self.assertNotContains(self.client.get(self.ad.get_absolute_url()), profile.phone)
        self.assertNotIn("phone", self.api.get(f"/api/v1/ads/{self.ad.pk}/").data)
        self.assertEqual(self.api.get(f"/api/v1/ads/{self.ad.pk}/contacts/").status_code, 401)
        self.authenticate(self.buyer)
        self.assertIsNone(self.api.get(f"/api/v1/ads/{self.ad.pk}/contacts/").data["phone"])
        profile.show_phone = True
        profile.save()
        self.assertEqual(
            self.api.get(f"/api/v1/ads/{self.ad.pk}/contacts/").data["phone"], profile.phone
        )
        self.assertContains(self.client.get(self.ad.get_absolute_url()), "tel:+79991234567")

    def test_conversation_is_private_and_reused(self):
        thread = start_conversation(ad=self.ad, user=self.buyer, text="Первое сообщение")
        same = start_conversation(ad=self.ad, user=self.buyer, text="Второе сообщение")
        self.assertEqual(thread.pk, same.pk)
        self.assertEqual(thread.messages.count(), 2)
        self.authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/messages/{thread.pk}/").status_code, 404)
        self.assertEqual(
            self.api.get(f"/api/v1/conversations/{thread.pk}/messages/").status_code, 404
        )
        self.assertEqual(self.api.get("/api/v1/conversations/").data["count"], 0)
        self.assertNotContains(self.client.get(self.ad.get_absolute_url()), "Первое сообщение")

    def test_seller_can_reply_and_read_messages(self):
        thread = start_conversation(ad=self.ad, user=self.buyer, text="В наличии?")
        self.authenticate(self.seller)
        response = self.api.post(f"/api/v1/conversations/{thread.pk}/messages/", {"text": "Да!"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get(f"/messages/{thread.pk}/").status_code, 200)
        self.assertIsNotNone(thread.messages.get(sender=self.buyer).read_at)
        self.assertIsNone(thread.messages.get(sender=self.seller).read_at)

    def test_message_poll_cursor_and_validation(self):
        thread = start_conversation(ad=self.ad, user=self.buyer, text="Первое")
        initial = thread.messages.first().pk
        self.authenticate(self.buyer)
        self.api.post(f"/api/v1/conversations/{thread.pk}/messages/", {"text": "Второе"})
        data = self.api.get(f"/api/v1/conversations/{thread.pk}/messages/?after={initial}").data
        self.assertEqual([row["text"] for row in data["results"]], ["Второе"])
        self.assertEqual(
            self.api.get(f"/api/v1/conversations/{thread.pk}/messages/?after=oops").status_code, 400
        )
        self.assertEqual(
            self.api.post(
                f"/api/v1/conversations/{thread.pk}/messages/", {"text": "   "}
            ).status_code,
            400,
        )

    def test_cannot_contact_self_or_closed_ad(self):
        with self.assertRaises(ValidationError):
            start_conversation(ad=self.ad, user=self.seller, text="self")
        self.ad.status = "closed"
        self.ad.save()
        with self.assertRaises(ValidationError):
            start_conversation(ad=self.ad, user=self.buyer, text="closed")

    def test_only_seller_accepts_and_reviews_require_interaction(self):
        self.authenticate(self.buyer)
        self.assertEqual(
            self.api.post(
                "/api/v1/reviews/", {"to_user": self.seller.pk, "rating": 5, "text": "Отлично"}
            ).status_code,
            400,
        )
        thread = start_conversation(ad=self.ad, user=self.buyer, text="Куплю")
        self.assertEqual(
            self.api.post(f"/api/v1/conversations/{thread.pk}/accept/").status_code, 403
        )
        self.authenticate(self.seller)
        self.assertEqual(
            self.api.post(f"/api/v1/conversations/{thread.pk}/accept/").status_code, 200
        )
        self.authenticate(self.buyer)
        self.assertEqual(
            self.api.post(
                "/api/v1/reviews/", {"to_user": self.seller.pk, "rating": 5, "text": "Отлично"}
            ).status_code,
            201,
        )
        self.assertEqual(
            self.api.post("/api/v1/reviews/", {"to_user": self.seller.pk, "rating": 4}).status_code,
            400,
        )
        self.assertEqual(
            self.api.post("/api/v1/reviews/", {"to_user": self.buyer.pk, "rating": 5}).status_code,
            400,
        )

    def test_database_rating_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.create(from_user=self.buyer, to_user=self.seller, rating=9)

    def test_favorite_api_is_idempotent(self):
        self.authenticate(self.buyer)
        url = f"/api/v1/ads/{self.ad.pk}/favorite/"
        self.assertEqual(self.api.post(url).status_code, 200)
        self.api.post(url)
        self.assertEqual(Favorite.objects.count(), 1)
        self.assertEqual(self.api.get("/api/v1/ads/favorites/").data["count"], 1)
        self.api.delete(url)
        self.api.delete(url)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_api_crud_price_normalization_and_search(self):
        self.authenticate(self.buyer)
        response = self.api.post(
            "/api/v1/ads/",
            {
                "title": "Стул",
                "description": "Для общежития",
                "price_type": "free",
                "category": self.category.pk,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["price"], "0.00")
        pk = response.data["id"]
        self.assertEqual(
            self.api.patch(f"/api/v1/ads/{pk}/", {"price_type": "negotiable"}).status_code, 200
        )
        self.assertEqual(
            self.api.patch(f"/api/v1/ads/{pk}/", {"price_type": "fixed", "price": -1}).status_code,
            400,
        )
        self.assertEqual(self.api.get("/api/v1/ads/?q=конспекты").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/ads/?price_max=10").data["count"], 0)
        self.assertEqual(self.api.delete(f"/api/v1/ads/{pk}/").status_code, 204)

    def test_api_cannot_assign_another_author(self):
        self.authenticate(self.buyer)
        response = self.api.post(
            "/api/v1/ads/",
            {
                "title": "Книга",
                "description": "Описание",
                "price": "100",
                "category": self.category.pk,
                "author": self.seller.pk,
            },
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Ad.objects.get(pk=response.data["id"]).author, self.buyer)

    @staticmethod
    def image_upload():
        buffer = BytesIO()
        Image.new("RGB", (40, 30), "#2557e0").save(buffer, "PNG")
        return SimpleUploadedFile("image.png", buffer.getvalue(), content_type="image/png")

    def test_images_are_validated_reencoded_and_limited(self):
        self.authenticate(self.seller)
        url = f"/api/v1/ads/{self.ad.pk}/photos/"
        response = self.api.post(url, {"images": [self.image_upload()]}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        photo = self.ad.images.get()
        self.assertTrue(photo.image.name.endswith(".jpg"))
        bad = SimpleUploadedFile(
            "attack.jpg", b"<script>alert(1)</script>", content_type="image/jpeg"
        )
        self.assertEqual(self.api.post(url, {"images": [bad]}, format="multipart").status_code, 400)
        self.assertEqual(
            self.api.post(
                url, {"images": [self.image_upload() for _ in range(8)]}, format="multipart"
            ).status_code,
            400,
        )
        self.authenticate(self.buyer)
        self.assertEqual(self.api.delete(f"/api/v1/photos/{photo.pk}/").status_code, 404)
        self.assertEqual(
            self.api.post(url, {"images": [self.image_upload()]}, format="multipart").status_code,
            403,
        )

    def test_registration_and_jwt_rotation_logout(self):
        data = {
            "username": "newstudent",
            "first_name": "Анна",
            "email": "anna@example.org",
            "password1": "A-very-strong-password-582!",
            "password2": "A-very-strong-password-582!",
        }
        self.assertEqual(self.api.post("/api/v1/auth/register/", data).status_code, 201)
        tokens = self.api.post(
            "/api/v1/auth/token/", {"username": data["username"], "password": data["password1"]}
        )
        self.assertEqual(tokens.status_code, 200, tokens.data)
        self.api.credentials(HTTP_AUTHORIZATION="Bearer " + tokens.data["access"])
        self.assertEqual(self.api.get("/api/v1/me/").status_code, 200)
        rotated = self.api.post("/api/v1/auth/token/refresh/", {"refresh": tokens.data["refresh"]})
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(
            self.api.post(
                "/api/v1/auth/token/refresh/", {"refresh": tokens.data["refresh"]}
            ).status_code,
            401,
        )
        self.assertEqual(
            self.api.post("/api/v1/auth/logout/", {"refresh": rotated.data["refresh"]}).status_code,
            200,
        )
        self.assertEqual(
            self.api.post(
                "/api/v1/auth/token/refresh/", {"refresh": rotated.data["refresh"]}
            ).status_code,
            401,
        )

    def test_profile_validation_and_private_fields(self):
        self.authenticate(self.buyer)
        self.assertEqual(
            self.api.patch("/api/v1/me/", {"phone": "javascript:bad"}).status_code, 400
        )
        self.assertEqual(
            self.api.patch(
                "/api/v1/me/", {"phone": "+79991234567", "first_name": "Анна", "show_phone": True}
            ).status_code,
            200,
        )
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.first_name, "Анна")
        data = self.api.get("/api/v1/users/buyer/").data
        self.assertNotIn("phone", data)
        self.assertNotIn("email", data)

    def test_session_api_mutations_enforce_csrf(self):
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(self.buyer)
        self.assertEqual(api.post(f"/api/v1/ads/{self.ad.pk}/favorite/").status_code, 403)

    def test_web_create_edit_and_delete(self):
        self.authenticate(self.buyer)
        data = {
            "title": "Настольная лампа",
            "description": "Работает",
            "category": self.category.pk,
            "kind": "sell",
            "price_type": "fixed",
            "price": "500",
            "condition": "used",
            "location": "Кампус",
            "status": "active",
        }
        response = self.client.post("/ad/create/", data)
        self.assertEqual(response.status_code, 302)
        ad = Ad.objects.get(title=data["title"])
        self.assertEqual(ad.author, self.buyer)
        data.update(price_type="free", price="", status="closed")
        self.assertEqual(self.client.post(f"/ad/{ad.pk}/update/", data).status_code, 302)
        ad.refresh_from_db()
        self.assertEqual(ad.price, 0)
        self.assertEqual(ad.status, "closed")
        self.assertEqual(self.client.post(f"/ad/{ad.pk}/delete/").status_code, 302)
        self.assertFalse(Ad.objects.filter(pk=ad.pk).exists())

    def test_web_profile_and_registration(self):
        self.authenticate(self.buyer)
        data = {
            "first_name": "Анна",
            "last_name": "Иванова",
            "faculty": "ИМИ",
            "group": "ИВТ-21",
            "role": "student",
            "phone": "+79991234567",
            "show_phone": True,
            "telegram": "anna_student",
            "bio": "Учусь и делюсь",
        }
        self.assertEqual(self.client.post("/profile/edit/", data).status_code, 302)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.first_name, "Анна")
        self.assertTrue(self.buyer.profile.show_phone)
        self.client.logout()
        data = {
            "username": "webstudent",
            "first_name": "Иван",
            "email": "ivan@example.org",
            "password1": "A-very-strong-password-582!",
            "password2": "A-very-strong-password-582!",
        }
        self.assertEqual(self.client.post("/register/", data).status_code, 302)
        self.assertTrue(User.objects.get(username="webstudent").check_password(data["password1"]))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_recovery_email(self):
        from django.core import mail

        response = self.client.post("/accounts/password_reset/", {"email": self.seller.email})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)

    def test_database_requires_zero_price_for_free_ads(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ad.objects.create(
                title="Bad",
                description="Bad",
                price=None,
                price_type="free",
                category=self.category,
                author=self.seller,
            )

    def test_api_can_remove_cover(self):
        self.ad.image = self.image_upload()
        save_ad(ad=self.ad, author=self.seller)
        self.authenticate(self.seller)
        response = self.api.patch(f"/api/v1/ads/{self.ad.pk}/", {"image": None})
        self.assertEqual(response.status_code, 200, response.data)
        self.ad.refresh_from_db()
        self.assertFalse(self.ad.image)

    @override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=2)
    def test_login_lockout_applies_to_jwt(self):
        for _ in range(2):
            self.api.post("/api/v1/auth/token/", {"username": "seller", "password": "incorrect"})
        response = self.api.post(
            "/api/v1/auth/token/", {"username": "seller", "password": "Strong-password-471!"}
        )
        self.assertEqual(response.status_code, 401)

    def test_messenger_sidebar_is_private_and_previews_latest_message(self):
        own = start_conversation(ad=self.ad, user=self.buyer, text="Первое сообщение")
        foreign = start_conversation(
            ad=self.ad, user=self.outsider, text="Секрет другого покупателя"
        )
        from .services import send_message

        send_message(conversation=own, sender=self.seller, text="Последний ответ продавца")
        self.authenticate(self.buyer)
        response = self.client.get("/messages/sidebar/", {"active": foreign.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["unread_total"], 1)
        self.assertIn("Последний ответ продавца", data["html"])
        self.assertNotIn("Секрет другого покупателя", data["html"])
        self.assertEqual(data["read_ids"], [])
        self.assertIsNone(own.messages.get(sender=self.seller).read_at)
        self.assertIn("no-store", response["Cache-Control"])

    def test_messenger_fragment_preserves_access_checks_and_marks_received_read(self):
        thread = start_conversation(ad=self.ad, user=self.buyer, text="Личный текст")
        self.authenticate(self.seller)
        response = self.client.get(f"/messages/{thread.pk}/", HTTP_X_MESSENGER_REQUEST="true")
        self.assertContains(response, "data-messenger")
        self.assertNotContains(response, "<!DOCTYPE html>")
        self.assertContains(response, "Личный текст")
        self.assertIsNotNone(thread.messages.get().read_at)
        self.assertIn("X-Messenger-Request", response["Vary"])
        self.authenticate(self.outsider)
        self.assertEqual(
            self.client.get(f"/messages/{thread.pk}/", HTTP_X_MESSENGER_REQUEST="true").status_code,
            404,
        )
        self.assertNotContains(
            self.client.get("/messages/", HTTP_X_MESSENGER_REQUEST="true"), "Личный текст"
        )

    def test_detail_reuses_conversation_and_invalid_contact_retains_text(self):
        self.authenticate(self.buyer)
        invalid = self.client.post(f"/ad/{self.ad.pk}/contact/", {"text": "x" * 4001})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.context["message_form"].data["text"], "x" * 4001)
        self.assertFalse(Response.objects.exists())
        thread = start_conversation(ad=self.ad, user=self.buyer, text="Здравствуйте")
        response = self.client.get(self.ad.get_absolute_url())
        self.assertEqual(response.context["existing_conversation"].pk, thread.pk)
        self.assertContains(response, "Продолжить переписку")
        self.assertNotContains(response, 'id="contact-form"')

    def test_photo_replacement_keeps_limit_and_remaining_order(self):
        from .models import AdImage
        from django.core.exceptions import PermissionDenied

        self.ad.image = self.image_upload()
        save_ad(ad=self.ad, author=self.seller, photos=[self.image_upload() for _ in range(7)])
        previous = list(self.ad.images.all())
        save_ad(
            ad=self.ad,
            author=self.seller,
            photos=[self.image_upload()],
            delete_photos=[previous[0]],
        )
        self.assertEqual(self.ad.images.count(), 7)
        self.assertFalse(AdImage.objects.filter(pk=previous[0].pk).exists())
        self.assertGreater(self.ad.images.last().position, previous[-1].position)
        with self.assertRaises(ValidationError):
            save_ad(ad=self.ad, author=self.seller, photos=[self.image_upload()])
        foreign = Ad.objects.create(
            author=self.outsider,
            category=self.category,
            title="Другая вещь",
            description="Описание",
            price=1,
        )
        save_ad(ad=foreign, author=self.outsider, photos=[self.image_upload()])
        with self.assertRaises(PermissionDenied):
            save_ad(ad=self.ad, author=self.seller, delete_photos=[foreign.images.get()])
        self.assertEqual(self.ad.images.count(), 7)

    def test_photo_deletion_waits_for_successful_form_save(self):
        save_ad(ad=self.ad, author=self.seller, photos=[self.image_upload()])
        photo = self.ad.images.get()
        self.authenticate(self.seller)
        data = {
            "title": "",
            "description": "Описание",
            "price_type": "fixed",
            "price": "450",
            "kind": "sell",
            "category": self.category.pk,
            "condition": "used",
            "location": "Кампус",
            "status": "active",
            "delete_photos": [photo.pk],
        }
        self.assertEqual(self.client.post(f"/ad/{self.ad.pk}/update/", data).status_code, 200)
        self.assertTrue(self.ad.images.filter(pk=photo.pk).exists())
        data["title"] = "Новое название"
        response = self.client.post(f"/ad/{self.ad.pk}/update/", data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.ad.images.exists())

    def test_photo_form_rejects_foreign_deletion_ids(self):
        from .forms import AdForm

        save_ad(ad=self.ad, author=self.seller, photos=[self.image_upload()])
        form = AdForm(
            {"delete_photos": [self.ad.images.get().pk]}, instance=Ad(author=self.outsider)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("delete_photos", form.errors)
        self.assertEqual(self.ad.images.count(), 1)

    def test_account_settings_persist_and_validate_contact_visibility(self):
        self.authenticate(self.buyer)
        response = self.client.post(
            "/settings/", {"phone": "", "show_phone": "on", "telegram": "", "reduce_motion": "on"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Укажите номер")
        self.assertFalse(profile_for(self.buyer).show_phone)
        response = self.client.post(
            "/settings/",
            {"phone": "+79991234567", "show_phone": "on", "telegram": "", "reduce_motion": "on"},
        )
        self.assertRedirects(response, "/settings/")
        profile = profile_for(self.buyer)
        self.assertTrue(profile.reduce_motion)
        self.assertTrue(profile.show_phone)
        self.assertContains(self.client.get("/"), 'class="reduce-motion ')
        self.client.logout()
        self.assertEqual(self.client.get("/settings/").status_code, 302)

    def test_new_information_and_password_pages_render(self):
        for page in ["about", "rules", "safety", "contacts"]:
            self.assertEqual(self.client.get(f"/info/{page}/").status_code, 200)
        self.assertEqual(self.client.get("/info/missing/").status_code, 404)
        self.authenticate(self.buyer)
        self.assertEqual(self.client.get("/accounts/password_change/").status_code, 200)
        self.assertEqual(self.client.get("/accounts/password_change/done/").status_code, 200)

    def test_password_change_keeps_session_and_requires_old_password(self):
        self.authenticate(self.buyer)
        response = self.client.post(
            "/accounts/password_change/",
            {
                "old_password": "wrong",
                "new_password1": "Changed-password-6841!",
                "new_password2": "Changed-password-6841!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.check_password("Strong-password-471!"))
        response = self.client.post(
            "/accounts/password_change/",
            {
                "old_password": "Strong-password-471!",
                "new_password1": "Changed-password-6841!",
                "new_password2": "Changed-password-6841!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/my-ads/").status_code, 200)

    def test_clear_cover_preserves_additional_photos(self):
        self.ad.image = self.image_upload()
        save_ad(ad=self.ad, author=self.seller, photos=[self.image_upload()])
        self.authenticate(self.seller)
        data = {
            "title": self.ad.title,
            "description": self.ad.description,
            "price_type": "fixed",
            "price": "450",
            "kind": "sell",
            "category": self.category.pk,
            "condition": "used",
            "location": "Кампус",
            "status": "active",
            "image-clear": "on",
        }
        response = self.client.post(f"/ad/{self.ad.pk}/update/", data)
        self.assertEqual(response.status_code, 302)
        self.ad.refresh_from_db()
        self.assertFalse(self.ad.image)
        self.assertEqual(self.ad.images.count(), 1)
        self.assertTrue(self.ad.cover)

    def test_admin_inline_enforces_eight_including_cover(self):
        from django.forms.models import inlineformset_factory
        from .admin import AdImageFormSet
        from .models import AdImage

        self.ad.image = self.image_upload()
        save_ad(ad=self.ad, author=self.seller)
        FormSet = inlineformset_factory(
            Ad, AdImage, formset=AdImageFormSet, fields=["image", "position"], extra=0
        )
        data = {"images-TOTAL_FORMS": "8", "images-INITIAL_FORMS": "0"}
        files = {}
        for index in range(8):
            data[f"images-{index}-position"] = index
            files[f"images-{index}-image"] = self.image_upload()
        formset = FormSet(data=data, files=files, instance=self.ad, prefix="images")
        self.assertFalse(formset.is_valid())
        self.assertIn("включая обложку", str(formset.non_form_errors()))

    def test_ajax_ad_form_saves_cover_and_all_additional_files(self):
        self.authenticate(self.seller)
        data = {
            "title": "Публикация с фотографиями",
            "description": "Тест загрузки по частям",
            "price_type": "fixed",
            "price": "650",
            "kind": "sell",
            "category": self.category.pk,
            "condition": "used",
            "location": "Кампус",
            "status": "active",
            "image": self.image_upload(),
            "photos": [self.image_upload() for _ in range(3)],
        }
        response = self.client.post("/ad/create/", data, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        ad = Ad.objects.get(pk=response.json()["id"])
        self.assertTrue(ad.image)
        self.assertEqual(ad.images.count(), 3)
        self.assertEqual(ad.status, "active")
        self.assertEqual(response.json()["redirect_url"], ad.get_absolute_url())
        self.assertIn("no-store", response["Cache-Control"])

    def test_ajax_validation_returns_errors_and_allows_corrected_retry(self):
        self.authenticate(self.seller)
        base = {
            "title": "Проверка ошибки фотографий",
            "description": "Описание",
            "price_type": "fixed",
            "price": "650",
            "kind": "sell",
            "category": self.category.pk,
            "condition": "used",
            "location": "Кампус",
            "status": "active",
        }
        bad = SimpleUploadedFile(
            "broken.jpg", b"not an actual photograph", content_type="image/jpeg"
        )
        response = self.client.post(
            "/ad/create/",
            {**base, "photos": [self.image_upload(), bad]},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("photos", response.json()["errors"])
        self.assertFalse(Ad.objects.filter(title=base["title"]).exists())
        response = self.client.post(
            "/ad/create/",
            {**base, "photos": [self.image_upload(), self.image_upload()]},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Ad.objects.get(pk=response.json()["id"]).images.count(), 2)

    def test_ajax_invalid_edit_does_not_remove_existing_photos(self):
        self.authenticate(self.seller)
        save_ad(ad=self.ad, author=self.seller, photos=[self.image_upload()])
        photo = self.ad.images.get()
        response = self.client.post(
            f"/ad/{self.ad.pk}/update/",
            {"title": "", "delete_photos": [photo.pk]},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.json()["errors"])
        self.assertTrue(self.ad.images.filter(pk=photo.pk).exists())

    def test_ajax_ad_submission_keeps_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.seller)
        self.assertEqual(
            client.post(
                "/ad/create/", {"title": "Атака"}, HTTP_ACCEPT="application/json"
            ).status_code,
            403,
        )
