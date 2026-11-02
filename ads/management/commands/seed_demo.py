"""Explicit, backed-up reset of the local demonstration database."""

import shutil
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from ads.categories import CATEGORIES
from ads.demo_data import DEMO_PASSWORD, LISTINGS, PEOPLE
from ads.models import Ad, Category, Favorite, Message, Response, Review, UserProfile
from ads.services import create_review, send_message, start_conversation
from ads.validators import validate_image

ASSETS_DIR = Path(__file__).resolve().parents[3] / "demo_assets"


class Command(BaseCommand):
    help = "Заполнить локальную демо-базу. --reset заменяет объявления и обычные аккаунты после резервного копирования."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Явно разрешить замену текущих данных; суперпользователи сохраняются.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG or connection.vendor != "sqlite":
            raise CommandError("Демо-сброс доступен только локально: DEBUG=true и SQLite.")
        User = get_user_model()
        if not options["reset"] and (
            Ad.objects.exists() or User.objects.filter(is_superuser=False).exists()
        ):
            raise CommandError("В базе уже есть данные. Для их замены явно передайте --reset.")
        # Validate every bundled asset before touching existing records.
        photos = {}
        for name in {row[2] for row in LISTINGS}:
            path = ASSETS_DIR / f"{name}.jpg"
            if not path.is_file():
                raise CommandError(f"Не найдено демо-фото: {path}")
            photos[name] = path.read_bytes()
            validate_image(ContentFile(photos[name], name=f"{name}.jpg"))
        backup_root = Path(settings.BASE_DIR) / "backups"
        backup_root.mkdir(exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_root / f"before-demo-reset-{stamp}.sqlite3"
        connection.ensure_connection()
        with closing(sqlite3.connect(backup)) as destination:
            connection.connection.backup(destination)
        if Path(settings.MEDIA_ROOT).is_dir():
            shutil.make_archive(
                str(backup_root / f"before-demo-media-{stamp}"), "zip", settings.MEDIA_ROOT
            )
        self.stdout.write(f"Резервная копия: {backup}")

        with transaction.atomic():
            Review.objects.all().delete()
            Message.objects.all().delete()
            Response.objects.all().delete()
            Favorite.objects.all().delete()
            Ad.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            Category.objects.all().delete()
            call_command("seed_categories", verbosity=0)
            people = []
            for username, first, last, faculty, group, role in PEOPLE:
                username = f"demo_{username}"
                if User.objects.filter(username=username).exists():
                    raise CommandError(
                        f"Имя {username} занято сохранённым администратором. Данные не изменены."
                    )
                user = User.objects.create_user(
                    username=username,
                    email=f"{username}@demo.example",
                    password=DEMO_PASSWORD,
                    first_name=first,
                    last_name=last,
                )
                UserProfile.objects.create(
                    user=user,
                    faculty=faculty,
                    group=group,
                    role=role,
                    bio="Демонстрационный профиль для проверки университетского маркетплейса.",
                )
                people.append(user)
            categories = {item.name: item for item in Category.objects.all()}
            locations = [
                "Библиотека СВФУ",
                "Кампус, ул. Кулаковского",
                "Учебный корпус",
                "Студенческий городок",
            ]
            listings = []
            now = timezone.now()
            for index, row in enumerate(LISTINGS):
                title, category, photo, price, owner, kind, price_type, description = row
                ad = Ad(
                    author=people[owner],
                    title=title,
                    category=categories[category],
                    price=price,
                    price_type=price_type,
                    kind=kind,
                    description=description,
                    condition="na" if kind in ("service", "roommate", "buy") else "used",
                    location=locations[index % len(locations)],
                )
                ad.image.save(f"{photo}.jpg", ContentFile(photos[photo]), save=False)
                ad.full_clean()
                ad.save()
                Ad.objects.filter(pk=ad.pk).update(
                    created_at=now - timedelta(minutes=index * 37),
                    updated_at=now - timedelta(minutes=index * 37),
                )
                listings.append(ad)
            # Examples in the cabinet: a draft and a completed listing.
            Ad.objects.create(
                author=people[0],
                title="Книги на следующий семестр",
                description="Черновик: добавлю список книг и фотографии позже.",
                category=categories["Учебники"],
                price_type="negotiable",
                price=None,
                status="draft",
            )
            Ad.objects.create(
                author=people[0],
                title="Стул — уже нашёл нового владельца",
                description="Пример закрытого объявления в личном кабинете.",
                category=categories["Мебель"],
                price=800,
                status="closed",
            )
            for index, ad in enumerate(listings[:6]):
                buyer = next(
                    user
                    for user in people[index + 1 :] + people[: index + 1]
                    if user.pk != ad.author_id
                )
                thread = start_conversation(
                    ad=ad,
                    user=buyer,
                    text="Здравствуйте! Объявление ещё актуально? Можно встретиться в кампусе?",
                )
                send_message(
                    conversation=thread,
                    sender=ad.author,
                    text="Здравствуйте! Да, актуально. Давайте согласуем удобное время здесь.",
                )
                if index < 4:
                    thread.is_accepted = True
                    thread.save(update_fields=["is_accepted"])
                    create_review(
                        author=buyer,
                        recipient=ad.author,
                        rating=5 if index != 2 else 4,
                        text="Быстро договорились, описание понятное. Спасибо за аккуратное общение!",
                    )
            for offset, user in enumerate(people[:4]):
                for ad in listings[offset + 2 : offset + 5]:
                    Favorite.objects.get_or_create(user=user, ad=ad)
        self.stdout.write(
            self.style.SUCCESS(
                "Готово: 12 категорий, 24 активных объявления, 2 примера для кабинета, 8 демо-аккаунтов. Администраторы сохранены."
            )
        )
        self.stdout.write("Логин: demo_anna. Пароль локальных демо-аккаунтов: " + DEMO_PASSWORD)
