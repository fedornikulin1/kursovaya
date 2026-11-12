"""Password login, including registrations pending when email checks were disabled."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db import transaction

from .models import EmailConfirmation


class RegistrationBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        authenticated = super().authenticate(request, username, password, **kwargs)
        if authenticated or settings.EMAIL_VERIFICATION_REQUIRED or password is None:
            return authenticated

        user_model = get_user_model()
        username = username or kwargs.get(user_model.USERNAME_FIELD)
        if username is None:
            return None
        with transaction.atomic():
            # Only an uncompleted registration can resume. Disabled established accounts
            # have no pending challenge, and staff accounts must be managed by an admin.
            user = user_model.objects.select_for_update().filter(
                **{user_model.USERNAME_FIELD: username},
                is_active=False,
                is_staff=False,
                is_superuser=False,
                email_confirmation__isnull=False,
            ).first()
            if user is None or not user.check_password(password):
                return None
            user.is_active = True
            user.save(update_fields=["is_active"])
            EmailConfirmation.objects.filter(user=user).delete()
            return user
