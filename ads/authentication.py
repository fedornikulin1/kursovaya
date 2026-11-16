"""Password login, including registrations pending when email checks were disabled."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import EmailConfirmation

APPROVED_STUDENTS = "Подтверждённые студенты СВФУ"


def may_sign_in(user):
    return bool(
        user and user.is_active and (
            not settings.STUDENT_ACCESS_ONLY
            or user.is_superuser
            or user.groups.filter(name=APPROVED_STUDENTS).exists()
        )
    )


def revoke_refresh_tokens(account):
    for token in OutstandingToken.objects.filter(user=account):
        BlacklistedToken.objects.get_or_create(token=token)


@transaction.atomic
def block_account(account_id, *, actor):
    if not actor.is_superuser or account_id == actor.pk:
        raise PermissionDenied
    account = get_user_model().objects.select_for_update().filter(pk=account_id).first()
    if not account:
        raise ValidationError("Аккаунт удалён.")
    if account.is_superuser:
        raise PermissionDenied
    if not account.is_active:
        return account, False
    account.is_active = False
    account.save(update_fields=["is_active"])
    EmailConfirmation.objects.filter(user=account).delete()
    revoke_refresh_tokens(account)
    return account, True


class CampusJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not may_sign_in(user):
            raise AuthenticationFailed("Доступ к площадке не подтверждён.")
        return user


class CampusJWTScheme(SimpleJWTScheme):
    target_class = CampusJWTAuthentication


class RegistrationBackend(ModelBackend):
    def user_can_authenticate(self, user):
        return may_sign_in(user)

    def authenticate(self, request, username=None, password=None, **kwargs):
        authenticated = super().authenticate(request, username, password, **kwargs)
        if (
            authenticated or settings.STUDENT_ACCESS_ONLY
            or settings.EMAIL_VERIFICATION_REQUIRED or password is None
        ):
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
