"""Add isolated study examples to existing demo accounts; never reset real data."""

from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from ads.models import Ad, Category
from ads.services import save_ad
from campus.models import CampusPlace, StudyRequest


class Command(BaseCommand):
    help = "Добавить учебные примеры существующим demo_* аккаунтам, без сброса базы"

    @transaction.atomic
    def handle(self, *args, **options):
        if (
            not settings.DEBUG
            or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3"
        ):
            raise CommandError(
                "Демонстрационные данные разрешены только локально с DEBUG и SQLite."
            )
        users = {
            user.username: user
            for user in get_user_model().objects.filter(
                username__in=["demo_anna", "demo_dmitry", "demo_alina", "demo_elena"]
            )
        }
        if len(users) != 4 or any(
            user.is_staff or user.is_superuser or not user.email.endswith("@demo.example")
            for user in users.values()
        ):
            raise CommandError(
                "Не найдены ожидаемые обычные demo_* аккаунты. Существующие данные не изменены."
            )
        category = Category.objects.filter(name="Учебники").first()
        if not category:
            raise CommandError("Сначала добавьте категорию «Учебники».")
        places = list(CampusPlace.objects.filter(is_active=True))
        if not places:
            raise CommandError("Добавьте хотя бы одно место в кампусе.")
        start = timezone.localtime().replace(
            hour=13, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        samples = [
            (
                "demo_dmitry",
                "Матанализ: учебник и мои разборы задач",
                "Математический анализ",
                1,
                2,
                "give",
                "",
                "Отдам учебник и собственные записи. Есть пометки на полях: удобно готовиться к коллоквиуму.",
            ),
            (
                "demo_alina",
                "Базы данных — учебник на следующий семестр",
                "Базы данных",
                2,
                3,
                "exchange",
                "Учебник по компьютерным сетям",
                "SQL, нормализация и проектирование. Обменяю на нужный мне учебник.",
            ),
            (
                "demo_elena",
                "Инженерный калькулятор на время сессии",
                "Физика",
                1,
                2,
                "lend",
                "",
                "Дам на время подготовки. Дату возврата согласуем в карточке встречи. Калькулятор рабочий, батарейки новые.",
            ),
            (
                "demo_dmitry",
                "Python: практикум для первокурсника",
                "Программирование",
                1,
                1,
                "sell",
                "",
                "Печатный практикум и личные заметки к упражнениям. Для самостоятельной подготовки.",
            ),
            (
                "demo_alina",
                "Собственные конспекты по линейной алгебре",
                "Линейная алгебра",
                1,
                1,
                "give",
                "",
                "Отдам свои конспекты с пояснениями и примерами. Удобно повторить определения перед зачётом.",
            ),
            (
                "demo_elena",
                "Английский: рабочая тетрадь и карточки",
                "Английский язык",
                1,
                2,
                "lend",
                "",
                "Можно взять на подготовку к зачёту. Вернуть в согласованную дату, карточки передать полным комплектом.",
            ),
        ]
        covers = list(
            Ad.objects.filter(category=category).exclude(image="").values_list("image", flat=True)
        )
        created = 0
        for index, (
            username,
            title,
            subject,
            course,
            semester,
            kind,
            exchange_for,
            description,
        ) in enumerate(samples):
            if Ad.objects.filter(author=users[username], title=title).exists():
                continue
            ad = Ad(
                author=users[username],
                title=title,
                subject=subject,
                course=course,
                semester=semester,
                kind=kind,
                exchange_for=exchange_for,
                description=description,
                category=category,
                is_study=True,
                campus_place=places[index % len(places)],
                available_from=start,
                available_until=start + timedelta(hours=3),
                price_type="fixed" if kind == "sell" else "free",
                price=500 if kind == "sell" else 0,
                image=covers[index % len(covers)] if covers else "",
            )
            save_ad(ad=ad, author=users[username])
            created += 1
        StudyRequest.objects.get_or_create(
            author=users["demo_anna"],
            title="Нужен учебник по матанализу к коллоквиуму",
            defaults={
                "subject": "Математический анализ",
                "course": 1,
                "semester": 2,
                "place": places[0],
                "available_from": start,
                "available_until": start + timedelta(hours=2),
                "description": "Подойдут учебник с пометками и собственные разборы задач. Могу забрать между парами.",
            },
        )
        StudyRequest.objects.get_or_create(
            author=users["demo_anna"],
            title="Калькулятор на подготовку к физике",
            defaults={
                "subject": "Физика",
                "course": 1,
                "semester": 2,
                "mode": "lend",
                "description": "Нужен инженерный калькулятор на неделю. Возврат согласуем заранее.",
            },
        )
        StudyRequest.objects.get_or_create(
            author=users["demo_dmitry"],
            title="Ищу учебник по базам данных",
            defaults={
                "subject": "Базы данных",
                "course": 2,
                "semester": 3,
                "mode": "exchange",
                "description": "Могу предложить учебник по компьютерным сетям.",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Добавлено учебных предложений: {created}. Примеры запросов готовы. Существующие объявления и аккаунты сохранены."
            )
        )
