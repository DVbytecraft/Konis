from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("produits", "0002_produit_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="produit",
            name="categorie",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="produits",
                to="produits.categorie",
            ),
        ),
    ]
