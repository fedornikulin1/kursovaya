from django.db import migrations


def seed_places(apps, schema_editor):
    Place = apps.get_model("campus", "CampusPlace")
    for name, hint in [
        ("Библиотека", "Общий холл у входа. Уточните ориентир в чате."),
        ("Учебный корпус", "Общий холл. Номер корпуса согласуйте в чате."),
        ("Студенческий городок", "Общественное место у входа. Уточните общежитие в чате."),
    ]:
        Place.objects.using(schema_editor.connection.alias).get_or_create(
            name=name, defaults={"meeting_hint": hint}
        )


class Migration(migrations.Migration):
    dependencies = [("campus", "0001_initial")]
    operations = [migrations.RunPython(seed_places, migrations.RunPython.noop)]
