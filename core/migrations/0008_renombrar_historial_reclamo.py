from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_historial_cartas"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="HistorialCarta",
            new_name="HistorialReclamo",
        ),
    ]
