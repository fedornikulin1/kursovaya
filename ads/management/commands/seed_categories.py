from django.core.management.base import BaseCommand
from ads.models import Category
from ads.categories import CATEGORIES


class Command(BaseCommand):
    help = "Создать стартовые категории; существующие объявления и пользователей не изменяет."

    def handle(self, *args, **options):
        for order, (name, icon) in enumerate(CATEGORIES):
            category, _ = Category.objects.get_or_create(name=name)
            category.icon = icon
            category.sort_order = order
            category.save(update_fields=["icon", "sort_order"])
        self.stdout.write(self.style.SUCCESS("Категории готовы."))
