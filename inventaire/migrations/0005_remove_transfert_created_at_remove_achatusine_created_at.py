from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0004_mouvementstock_unit_price_and_production_order"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="transfert",
            name="created_at",
        ),
        migrations.RemoveField(
            model_name="achatusine",
            name="created_at",
        ),
    ]
