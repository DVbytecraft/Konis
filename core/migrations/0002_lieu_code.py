# Generated for KONIS V0 - Lieu.code pour numéros ticket

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lieu",
            name="code",
            field=models.CharField(blank=True, default="", help_text="Code lieu pour numéros ticket (ex: KARA, CENTRE)", max_length=20),
        ),
    ]
