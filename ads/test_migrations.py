"""Exercise the legacy upgrade in a separate database, never the user's database."""

import copy
import tempfile
from pathlib import Path

from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase
from django.utils import timezone


class LegacyMigrationTests(SimpleTestCase):
    def test_upgrade_preserves_inactive_ads_images_messages_and_reviews(self):
        alias = "legacy_upgrade_check"
        with tempfile.TemporaryDirectory() as directory:
            config = copy.deepcopy(connections["default"].settings_dict)
            config.update(
                ENGINE="django.db.backends.sqlite3", NAME=str(Path(directory) / "legacy.sqlite3")
            )
            connections.databases[alias] = config
            connection = connections[alias]
            original_allowed = type(self).databases
            type(self).databases = frozenset({alias})
            try:
                executor = MigrationExecutor(connection)
                previous = [("ads", "0009_review")]
                executor.migrate(previous)
                old = executor.loader.project_state(previous).apps
                User = old.get_model("auth", "User")
                Category = old.get_model("ads", "Category")
                Ad = old.get_model("ads", "Ad")
                Response = old.get_model("ads", "Response")
                Review = old.get_model("ads", "Review")
                seller = User.objects.using(alias).create(username="legacy_seller")
                buyer = User.objects.using(alias).create(username="legacy_buyer")
                category = Category.objects.using(alias).create(name="История")
                ad = Ad.objects.using(alias).create(
                    title="Старая книга",
                    description="Сохранить",
                    price=250,
                    category=category,
                    author=seller,
                    is_active=False,
                    image="ads/original.jpg",
                )
                first = Response.objects.using(alias).create(
                    ad=ad, user=buyer, text="Первое", reply="Ответ один"
                )
                second = Response.objects.using(alias).create(
                    ad=ad, user=buyer, text="Второе", reply="Ответ два", is_accepted=True
                )
                Review.objects.using(alias).create(
                    to_user=seller, from_user=buyer, rating=4, text="Старый отзыв"
                )
                original_date = timezone.now()
                Response.objects.using(alias).filter(pk=first.pk).update(created_at=original_date)
                executor = MigrationExecutor(connection)
                target = [("ads", "0010_adimage_message_userprofile_alter_ad_options_and_more")]
                executor.migrate(target)
                current = executor.loader.project_state(target).apps
                upgraded = current.get_model("ads", "Ad").objects.using(alias).get(pk=ad.pk)
                self.assertEqual(upgraded.status, "archived")
                self.assertEqual(upgraded.image.name, "ads/original.jpg")
                threads = current.get_model("ads", "Response").objects.using(alias)
                self.assertEqual(threads.count(), 1)
                self.assertTrue(threads.get().is_accepted)
                messages = current.get_model("ads", "Message").objects.using(alias)
                self.assertCountEqual(
                    list(messages.values_list("text", flat=True)),
                    ["Первое", "Ответ один", "Второе", "Ответ два"],
                )
                self.assertEqual(messages.filter(text="Первое").get().created_at, original_date)
                self.assertEqual(
                    current.get_model("ads", "Review").objects.using(alias).get().rating, 4
                )
                self.assertEqual(
                    current.get_model("ads", "UserProfile").objects.using(alias).count(), 2
                )
            finally:
                connection.close()
                del connections[alias]
                del connections.databases[alias]
                type(self).databases = original_allowed
