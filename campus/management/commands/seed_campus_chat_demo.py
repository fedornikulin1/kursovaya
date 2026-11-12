"""Add a small example conversation to the local campus chat."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from campus.chat_moderation import validate_campus_chat_body
from campus.models import CampusMessage


MESSAGES = (
    (
        "calculator",
        "demo_anna",
        CampusMessage.Kind.WANTED,
        "У кого есть инженерный калькулятор на неделю? Нужен к зачёту по физике.",
        None,
    ),
    (
        "calculator_offer",
        "demo_dmitry",
        CampusMessage.Kind.GENERAL,
        "Есть запасной. Могу передать у библиотеки после второй пары.",
        "calculator",
    ),
    (
        "calculator_reply",
        "demo_anna",
        CampusMessage.Kind.GENERAL,
        "Спасибо! Напишу в личку, чтобы договориться о времени.",
        "calculator_offer",
    ),
    (
        "extension",
        "demo_alina",
        CampusMessage.Kind.WANTED,
        "Ищу удлинитель на три розетки для общежития. Может, у кого-то есть лишний?",
        None,
    ),
    (
        "extension_offer",
        "demo_mikhail",
        CampusMessage.Kind.GENERAL,
        "У меня есть трёхметровый, могу отдать. Давай уточним место в личных сообщениях.",
        "extension",
    ),
)


class Command(BaseCommand):
    help = "Добавить примеры в чат кампуса от существующих демо-аккаунтов"

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or connection.vendor != "sqlite":
            raise CommandError("Демо-чат доступен только локально: DEBUG=true и SQLite.")

        names = {username for _, username, _, _, _ in MESSAGES}
        users = {
            user.username: user
            for user in get_user_model().objects.filter(
                username__in=names, is_active=True, is_staff=False, is_superuser=False
            )
            if user.email == f"{user.username}@demo.example"
        }
        if set(users) != names:
            raise CommandError(
                "Не найдены ожидаемые демо-аккаунты. Сообщения не изменены."
            )

        messages = {}
        created_count = 0
        for key, username, kind, text, parent in MESSAGES:
            body = f"Демо · {text}"
            validate_campus_chat_body(body, wanted=kind == CampusMessage.Kind.WANTED)
            messages[key], created = CampusMessage.objects.get_or_create(
                author=users[username],
                body=body,
                defaults={"kind": kind, "reply_to": messages[parent] if parent else None},
            )
            created_count += created
        self.stdout.write(self.style.SUCCESS(f"Демо-сообщений добавлено: {created_count}."))
