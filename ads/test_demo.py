import sqlite3
from contextlib import closing
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from ads.demo_data import LISTINGS, PEOPLE, DEMO_PASSWORD
from ads.models import Ad, Category, Message, Review


class DemoDatasetTests(TransactionTestCase):
    @override_settings(DEBUG=False)
    def test_demo_reset_is_refused_in_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", reset=True, stdout=StringIO())

    @override_settings(DEBUG=True)
    def test_existing_data_requires_explicit_reset(self):
        get_user_model().objects.create_user("existing")
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertTrue(get_user_model().objects.filter(username="existing").exists())

    def test_reset_preserves_admin_backs_up_database_and_creates_consistent_examples(self):
        User = get_user_model()
        admin = User.objects.create_superuser(
            "administrator", "owner@example.org", "Owner-password-312!"
        )
        old_user = User.objects.create_user("old_account")
        category = Category.objects.create(name="Старая категория")
        Ad.objects.create(
            title="Старое объявление",
            description="Сохранить в копии",
            price=1,
            category=category,
            author=old_user,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            buffer = BytesIO()
            Image.new("RGB", (30, 30), "#2557e0").save(buffer, "JPEG")
            for name in {row[2] for row in LISTINGS}:
                (assets / f"{name}.jpg").write_bytes(buffer.getvalue())
            with (
                override_settings(
                    DEBUG=True,
                    BASE_DIR=root,
                    MEDIA_ROOT=root / "media",
                    STORAGES={
                        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                        "staticfiles": {
                            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                        },
                    },
                ),
                patch("ads.management.commands.seed_demo.ASSETS_DIR", assets),
            ):
                call_command("seed_demo", reset=True, stdout=StringIO())
                self.assertEqual(Ad.objects.filter(status="active").count(), 24)
                self.assertEqual(Ad.objects.count(), 26)
                self.assertEqual(Category.objects.count(), 12)
                self.assertEqual(User.objects.filter(is_superuser=False).count(), len(PEOPLE))
                self.assertTrue(User.objects.get(pk=admin.pk).check_password("Owner-password-312!"))
                self.assertFalse(User.objects.filter(username="old_account").exists())
                self.assertTrue(
                    User.objects.get(username="demo_anna").check_password(DEMO_PASSWORD)
                )
                self.assertEqual(Review.objects.count(), 4)
                self.assertEqual(Message.objects.count(), 12)
                for ad in Ad.objects.filter(status="active"):
                    self.assertTrue(ad.image.storage.exists(ad.image.name))
                    self.assertTrue(ad.image.url.startswith("/uploads/listings/"))
                    self.assertNotIn("/ads/", ad.image.url)
                    self.assertTrue(ad.author.email.endswith("@demo.example"))
                backup = next((root / "backups").glob("*.sqlite3"))
                with closing(sqlite3.connect(backup)) as database:
                    self.assertEqual(
                        database.execute("SELECT title FROM ads_ad").fetchone()[0],
                        "Старое объявление",
                    )
