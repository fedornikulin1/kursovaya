"""Web and API account access while email confirmation is optional."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .forms import RegisterForm
from .models import EmailConfirmation

User = get_user_model()


@override_settings(
    EMAIL_VERIFICATION_REQUIRED=False,
    AXES_ENABLED=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class RegistrationTests(TestCase):
    def setUp(self):
        # Auth throttling uses cache rather than the test database.
        cache.clear()
        self.addCleanup(cache.clear)

    def registration_data(self, **overrides):
        return {
            "username": "student",
            "first_name": "Анна",
            "email": "anna@example.org",
            "password1": "123456",
            "password2": "123456",
            **overrides,
        }

    @patch("ads.email_verification.send_confirmation")
    def test_web_registration_allows_six_digit_password_without_mail(self, send_code):
        response = self.client.post("/register/", self.registration_data())
        self.assertRedirects(response, "/accounts/login/")
        user = User.objects.get(username="student")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("123456"))
        self.assertNotIn("pending_confirmation_user", self.client.session)
        self.assertFalse(EmailConfirmation.objects.filter(user=user).exists())
        send_code.assert_not_called()
        self.assertTrue(self.client.login(username="student", password="123456"))

    @patch("ads.email_verification.send_confirmation")
    def test_api_registration_can_log_in_immediately(self, send_code):
        api = APIClient()
        response = api.post("/api/v1/auth/register/", self.registration_data())
        self.assertEqual(response.status_code, 201, response.data)
        tokens = api.post("/api/v1/auth/token/", {"username": "student", "password": "123456"})
        self.assertEqual(tokens.status_code, 200, tokens.data)
        self.assertIn("access", tokens.data)
        send_code.assert_not_called()

    def test_short_or_mismatched_password_is_rejected_in_web_and_api(self):
        for data in [
            self.registration_data(password1="12345", password2="12345"),
            self.registration_data(password2="654321"),
        ]:
            with self.subTest(data=data):
                self.assertFalse(RegisterForm(data).is_valid())
                response = APIClient().post("/api/v1/auth/register/", data)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="student").exists())

    def test_email_remains_required_valid_and_unique_case_insensitively(self):
        User.objects.create_user("existing", email="anna@example.org", password="123456")
        for email in ["", "not-an-email", "ANNA@EXAMPLE.ORG"]:
            with self.subTest(email=email):
                form = RegisterForm(self.registration_data(email=email))
                self.assertFalse(form.is_valid())
                self.assertIn("email", form.errors)

    def test_password_change_and_reset_use_same_minimum_length(self):
        user = User.objects.create_user("student", password="old-password")
        for form_class in [PasswordChangeForm, SetPasswordForm]:
            with self.subTest(form=form_class.__name__):
                short = form_class(user, data={
                    "old_password": "old-password", "new_password1": "12345", "new_password2": "12345",
                })
                self.assertFalse(short.is_valid())
                accepted = form_class(user, data={
                    "old_password": "old-password", "new_password1": "123456", "new_password2": "123456",
                })
                self.assertTrue(accepted.is_valid(), accepted.errors)

    def pending_user(self):
        user = User.objects.create_user("pending", email="pending@example.org", password="123456", is_active=False)
        EmailConfirmation.objects.create(user=user, code_hash="unused")
        return user

    def test_pending_registration_only_resumes_after_correct_password(self):
        user = self.pending_user()
        self.assertFalse(self.client.login(username="pending", password="incorrect"))
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(EmailConfirmation.objects.filter(user=user).exists())
        self.assertTrue(self.client.login(username="pending", password="123456"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(EmailConfirmation.objects.filter(user=user).exists())

    def test_api_login_also_resumes_pending_registration(self):
        user = self.pending_user()
        response = APIClient().post("/api/v1/auth/token/", {"username": "pending", "password": "123456"})
        self.assertEqual(response.status_code, 200, response.data)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_disabled_established_or_staff_account_is_not_reactivated(self):
        User.objects.create_user("blocked", password="123456", is_active=False)
        staff = self.pending_user()
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        for username in ["blocked", "pending"]:
            with self.subTest(username=username):
                self.assertFalse(self.client.login(username=username, password="123456"))
                self.assertFalse(User.objects.get(username=username).is_active)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_pending_registration_cannot_bypass_enabled_confirmation(self):
        self.pending_user()
        self.assertFalse(self.client.login(username="pending", password="123456"))

    @patch("ads.email_verification.send_confirmation")
    def test_old_confirmation_routes_do_not_send_codes_when_disabled(self, send_code):
        self.pending_user()
        self.assertRedirects(self.client.get("/register/confirm/"), "/accounts/login/")
        api = APIClient()
        for url in ["/api/v1/auth/confirm-email/", "/api/v1/auth/resend-code/"]:
            self.assertEqual(api.post(url, {"username": "pending", "code": "123456"}).status_code, 404)
        send_code.assert_not_called()
        self.assertFalse(User.objects.get(username="pending").is_active)
