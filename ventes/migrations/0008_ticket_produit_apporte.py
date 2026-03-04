from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0007_add_mouture_to_ticket"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="produit_apporte",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Produit apporté par le client",
            ),
        ),
    ]
