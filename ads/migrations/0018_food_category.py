from django.db import migrations


def seed(apps, schema_editor):
    Category = apps.get_model("ads", "Category")
    Category.objects.get_or_create(name="Продукты", defaults={"icon": "grid", "sort_order": 1})


class Migration(migrations.Migration):
    dependencies = [("ads", "0017_ad_dormitory_userprofile_dormitory")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
