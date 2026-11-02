"""Integration coverage for ranking, privacy and handover state transitions."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from ads.forms import AdForm
from ads.models import Ad, Category, Response
from ads.services import delete_ad, save_ad, start_conversation
from .models import CampusPlace, Meeting, StudyRequest
from .selectors import ranked_matches
from .services import meeting_action, propose_meeting, respond_to_request


@override_settings(
    AXES_ENABLED=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class CampusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.seller = User.objects.create_user("study_seller", password="Strong-test-2026!")
        cls.buyer = User.objects.create_user("study_buyer", password="Strong-test-2026!")
        cls.other = User.objects.create_user("study_other", password="Strong-test-2026!")
        cls.place = CampusPlace.objects.create(name="Тестовый корпус", meeting_hint="Холл")
        cls.category = Category.objects.create(name="Тестовые учебники")
        cls.ad = Ad.objects.create(
            author=cls.seller,
            title="Учебник",
            description="Учебный пример",
            category=cls.category,
            price=0,
            price_type="free",
            kind="give",
            is_study=True,
            subject="Базы данных",
            course=2,
            semester=3,
            campus_place=cls.place,
        )
        cls.thread = Response.objects.create(ad=cls.ad, user=cls.buyer)

    def setUp(self):
        self.api = APIClient()
        self.start = timezone.now() + timedelta(hours=1)
        self.end = self.start + timedelta(hours=1)

    def proposal(self, **kwargs):
        data = dict(
            conversation=self.thread,
            user=self.buyer,
            place=self.place,
            starts_at=self.start,
            ends_at=self.end,
        )
        data.update(kwargs)
        return propose_meeting(**data)

    def act(self, meeting, user, action):
        return meeting_action(meeting=meeting, user=user, action=action)

    def test_public_pages_and_private_mine(self):
        for url in ("/", "/campus/", "/campus/?tab=requests", self.ad.get_absolute_url()):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/campus/?tab=mine").status_code, 302)
        self.client.force_login(self.buyer)
        for url in (
            "/campus/?tab=mine",
            "/campus/requests/new/",
            "/ad/create/?study=1",
            f"/messages/{self.thread.pk}/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_matches_explain_score_and_fold_cyrillic_case(self):
        self.ad.available_from, self.ad.available_until = self.start, self.end
        self.ad.save()
        need = StudyRequest.objects.create(
            author=self.buyer,
            title="Нужно",
            subject="БАЗЫ ДАННЫХ",
            course=2,
            semester=3,
            place=self.place,
            available_from=self.start,
            available_until=self.end,
        )
        matches = ranked_matches(need, self.buyer)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["score"], 100)
        self.assertEqual(len(matches[0]["reasons"]), 5)
        self.ad.author = self.buyer
        self.ad.save()
        self.assertEqual(ranked_matches(need), [])

    def test_search_folds_cyrillic_in_catalogue_and_api_subject_filter(self):
        self.assertContains(self.client.get("/campus/", {"q": "базы ДАННЫХ"}), "Учебник")
        result = self.api.get("/api/v1/ads/", {"is_study": "true", "subject": "базы ДАННЫХ"})
        self.assertEqual(result.data["count"], 1)

    def test_matching_ignores_unrelated_expired_reserved_and_wrong_mode(self):
        need = StudyRequest.objects.create(
            author=self.buyer, title="Нужно", subject="Физика", mode="lend"
        )
        self.assertEqual(ranked_matches(need), [])
        need.subject, need.mode = "Базы данных", "any"
        meeting = self.proposal()
        self.act(meeting, self.seller, "confirm")
        self.assertEqual(ranked_matches(need), [])
        self.act(meeting, self.buyer, "cancel")
        self.assertEqual(len(ranked_matches(need)), 1)
        self.ad.available_from, self.ad.available_until = timezone.now() - timedelta(
            days=2
        ), timezone.now() - timedelta(days=1)
        self.ad.save()
        self.assertEqual(ranked_matches(need), [])

    def test_proposal_does_not_reserve_and_cannot_self_confirm(self):
        meeting = self.proposal()
        with self.assertRaises(ValidationError):
            self.act(meeting, self.buyer, "confirm")
        self.assertEqual(Meeting.objects.get().status, "proposed")
        with self.assertRaises(PermissionDenied):
            self.act(meeting, self.other, "confirm")
        self.assertEqual(self.act(meeting, self.seller, "confirm").status, "confirmed")

    def test_no_double_reservation_and_cancel_releases(self):
        first = self.proposal()
        second_thread = Response.objects.create(ad=self.ad, user=self.other)
        second = self.proposal(conversation=second_thread, user=self.other)
        self.act(first, self.seller, "confirm")
        with self.assertRaises(ValidationError):
            self.act(second, self.seller, "confirm")
        self.act(first, self.buyer, "cancel")
        self.assertEqual(self.act(second, self.seller, "confirm").status, "confirmed")

    def test_database_prevents_second_live_reservation(self):
        first = self.proposal()
        self.act(first, self.seller, "confirm")
        other_thread = Response.objects.create(ad=self.ad, user=self.other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Meeting.objects.create(
                ad=self.ad,
                conversation=other_thread,
                proposed_by=self.other,
                place=self.place,
                starts_at=self.start,
                ends_at=self.end,
                status="confirmed",
            )

    def test_expiry_is_effective_on_read_without_mutation_and_releases_on_write(self):
        meeting = self.proposal()
        self.act(meeting, self.seller, "confirm")
        Meeting.objects.filter(pk=meeting.pk).update(
            starts_at=timezone.now() - timedelta(hours=2),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        meeting.refresh_from_db()
        self.assertEqual(meeting.effective_status, "expired")
        self.assertEqual(Meeting.objects.get(pk=meeting.pk).status, "confirmed")
        fresh = self.proposal()
        self.assertEqual(Meeting.objects.get(pk=meeting.pk).status, "expired")
        self.assertEqual(self.act(fresh, self.seller, "confirm").status, "confirmed")

    def test_complete_gift_requires_both_participants_and_closes_listing_and_request(self):
        need = StudyRequest.objects.create(author=self.buyer, title="Нужно", subject="Базы данных")
        meeting = self.proposal(study_request=need)
        self.act(meeting, self.seller, "confirm")
        with self.assertRaises(ValidationError):
            self.act(meeting, self.seller, "handover")
        with patch("campus.services.timezone.now", return_value=self.start + timedelta(minutes=5)):
            self.act(meeting, self.seller, "handover")
            with self.assertRaises(ValidationError):
                self.act(meeting, self.seller, "receive")
            self.assertEqual(self.act(meeting, self.buyer, "receive").status, "completed")
        self.ad.refresh_from_db()
        self.thread.refresh_from_db()
        need.refresh_from_db()
        self.assertEqual(self.ad.status, "closed")
        self.assertTrue(self.thread.is_accepted)
        self.assertFalse(need.is_active)

    def test_loan_receipt_return_and_release(self):
        self.ad.kind = "lend"
        self.ad.save()
        with self.assertRaises(ValidationError):
            self.proposal()
        meeting = self.proposal(return_on=timezone.localdate(self.end) + timedelta(days=7))
        self.act(meeting, self.seller, "confirm")
        with patch("campus.services.timezone.now", return_value=self.start + timedelta(minutes=5)):
            self.act(meeting, self.seller, "handover")
        self.assertEqual(self.act(meeting, self.buyer, "receive").status, "on_loan")
        with self.assertRaises(ValidationError):
            self.act(meeting, self.buyer, "cancel")
        with self.assertRaises(ValidationError):
            self.act(meeting, self.seller, "finish_return")
        self.act(meeting, self.buyer, "return")
        self.assertEqual(self.act(meeting, self.seller, "finish_return").status, "completed")
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.status, "active")
        self.assertEqual(
            self.proposal(return_on=timezone.localdate(self.end) + timedelta(days=8)).status,
            "proposed",
        )

    def test_occupied_listing_cannot_be_retyped_archived_or_deleted(self):
        meeting = self.proposal()
        self.act(meeting, self.seller, "confirm")
        with self.assertRaises(ValidationError):
            delete_ad(ad=self.ad, user=self.seller)
        self.ad.kind = "sell"
        with self.assertRaises(ValidationError):
            save_ad(ad=self.ad, author=self.seller)
        self.api.force_authenticate(self.seller)
        self.assertEqual(self.api.delete(f"/api/v1/ads/{self.ad.pk}/").status_code, 400)

    def test_dates_own_request_and_place_are_validated(self):
        for values in (
            {"starts_at": self.end, "ends_at": self.start},
            {"ends_at": self.start + timedelta(hours=5)},
            {"starts_at": timezone.now() - timedelta(hours=1)},
        ):
            with self.assertRaises(ValidationError):
                self.proposal(**values)
        foreign = StudyRequest.objects.create(
            author=self.other, title="Чужое", subject="Базы данных"
        )
        with self.assertRaises(ValidationError):
            self.proposal(study_request=foreign)
        self.place.is_active = False
        self.place.save()
        with self.assertRaises(ValidationError):
            self.proposal()

    def test_api_and_html_permissions_and_csrf(self):
        meeting = self.proposal()
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(f"/api/v1/campus/meetings/{meeting.pk}/").status_code, 404)
        self.assertEqual(self.api.get("/api/v1/campus/meetings/").data["count"], 0)
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/campus/conversations/{self.thread.pk}/meeting/").status_code, 404
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.seller)
        self.assertEqual(
            client.post(
                f"/campus/meetings/{meeting.pk}/action/", {"action": "confirm"}
            ).status_code,
            403,
        )
        self.assertEqual(client.get(f"/campus/meetings/{meeting.pk}/action/").status_code, 405)

    def test_request_api_owner_validation_and_matches(self):
        self.api.force_authenticate(self.buyer)
        response = self.api.post(
            "/api/v1/campus/requests/",
            {"title": "Нужно", "subject": "Базы данных", "author": self.seller.pk, "course": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        need = StudyRequest.objects.get(pk=response.data["id"])
        self.assertEqual(need.author_id, self.buyer.pk)
        self.assertEqual(len(self.api.get(f"/api/v1/campus/requests/{need.pk}/matches/").data), 1)
        self.assertEqual(
            self.api.patch(
                f"/api/v1/campus/requests/{need.pk}/", {"course": 7}, format="json"
            ).status_code,
            400,
        )
        self.api.force_authenticate(self.other)
        self.assertEqual(
            self.api.patch(f"/api/v1/campus/requests/{need.pk}/", {"title": "x"}).status_code, 403
        )
        self.assertEqual(
            self.api.get(f"/api/v1/campus/requests/{need.pk}/matches/").status_code, 403
        )

    def test_api_create_and_transition(self):
        self.api.force_authenticate(self.buyer)
        response = self.api.post(
            "/api/v1/campus/meetings/",
            {
                "conversation": self.thread.pk,
                "place": self.place.pk,
                "starts_at": self.start.isoformat(),
                "ends_at": self.end.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.api.force_authenticate(self.seller)
        confirmed = self.api.post(
            f"/api/v1/campus/meetings/{response.data['id']}/transition/",
            {"action": "confirm"},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["status"], "confirmed")

    def test_exchange_price_normalized_for_form_and_api(self):
        self.api.force_authenticate(self.seller)
        result = self.api.patch(
            f"/api/v1/ads/{self.ad.pk}/",
            {"kind": "exchange", "price_type": "fixed", "price": 500},
            format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.price, 0)
        self.assertEqual(self.ad.price_label, "Обмен")

    def test_offer_request_creates_private_thread_once(self):
        need = StudyRequest.objects.create(author=self.buyer, title="Нужно", subject="Базы данных")
        self.thread.delete()
        first = respond_to_request(study_request=need, ad=self.ad, user=self.seller)
        second = respond_to_request(study_request=need, ad=self.ad, user=self.seller)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.messages.count(), 1)
        with self.assertRaises(PermissionDenied):
            respond_to_request(study_request=need, ad=self.ad, user=self.other)

    def test_api_offer_request_and_invalid_web_meeting_keep_errors_visible(self):
        need = StudyRequest.objects.create(author=self.buyer, title="Нужно", subject="Базы данных")
        self.api.force_authenticate(self.seller)
        offered = self.api.post(
            f"/api/v1/campus/requests/{need.pk}/offer/", {"ad": self.ad.pk}, format="json"
        )
        self.assertEqual(offered.status_code, 200, offered.data)
        self.assertEqual(offered.data["id"], self.thread.pk)
        self.client.force_login(self.buyer)
        response = self.client.post(
            f"/campus/conversations/{self.thread.pk}/meeting/",
            {
                "place": self.place.pk,
                "starts_at": self.end.isoformat(),
                "ends_at": self.start.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'class="campus-meeting" open', status_code=400)
        self.assertContains(response, "Выберите будущую встречу", status_code=400)
