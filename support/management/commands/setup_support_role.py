from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the support operator role without granting access to any user."

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name="Поддержка")
        group.permissions.set(
            Permission.objects.filter(
                content_type__app_label="support",
                codename__in=["view_supportticket", "change_supportticket", "view_faq"],
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Роль «Поддержка» готова. Назначьте её сотруднику и включите доступ к админке в карточке пользователя."
            )
        )
