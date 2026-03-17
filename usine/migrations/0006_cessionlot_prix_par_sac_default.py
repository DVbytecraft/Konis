from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usine", "0005_add_missing_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transfertcession",
            name="prix_par_sac",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name="Prix de vente par sac",
            ),
        ),
    ]
