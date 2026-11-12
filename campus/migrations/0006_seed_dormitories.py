from django.db import migrations


def seed(apps, schema_editor):
    Dormitory = apps.get_model("campus", "Dormitory")
    entries = [
        ("Общежитие № 1", "Сергеляхская, 2, корпус 14"),
        ("Общежитие № 2", "Сергеляхская, 2, корпус 17"),
        ("Общежитие № 3", "Сергеляхская, 2, корпус 18"),
        ("Общежитие № 4", "Сергеляхская, 2, корпус 20"),
        ("Общежитие № 6-А", "Каландарашвили, 17"),
        ("Общежитие № 6-Б", "Каландарашвили, 17"),
        ("Общежитие № 6-В", "Каландарашвили, 17"),
        ("Общежитие № 7/1", "Кулаковского, 46/1"),
        ("Общежитие № 7/2", "Кулаковского, 46/1"),
        ("Общежитие № 8/1", "Кулаковского, 46/2"),
        ("Общежитие № 8/2", "Кулаковского, 46/2"),
        ("Общежитие № 9/1", "Кулаковского, 42/2"),
        ("Общежитие № 9/2", "Кулаковского, 42/2"),
        ("Общежитие ТИ № 1", "Строителей, 8/1"),
        ("Общежитие ТИ № 2", "Строителей, 8/2"),
    ]
    for name, address in entries:
        Dormitory.objects.get_or_create(name=name, defaults={"address": address})


class Migration(migrations.Migration):
    dependencies = [("campus", "0005_dormitory_campusmessage_dormitory")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
