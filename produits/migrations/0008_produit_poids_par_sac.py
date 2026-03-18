from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("produits", "0007_alter_produit_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="produit",
            name="poids_par_sac",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Poids d'un sac de ce produit en kg. Requis si l'unité est 'sac' et que la mouture est utilisée.",
                max_digits=8,
                null=True,
                verbose_name="Poids par sac (kg)",
            ),
        ),
    ]
