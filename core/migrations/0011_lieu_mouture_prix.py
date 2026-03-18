from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_finance_app_et_nouveaux_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="lieu",
            name="prix_mouture_defaut",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Pré-rempli automatiquement dans le formulaire de saisie.",
                max_digits=10,
                null=True,
                verbose_name="Prix mouture par défaut (FCFA/kg)",
            ),
        ),
        migrations.AddField(
            model_name="lieu",
            name="prix_mouture_max",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Si défini, tout prix supérieur est refusé sans autorisation admin.",
                max_digits=10,
                null=True,
                verbose_name="Prix mouture maximum autorisé (FCFA/kg)",
            ),
        ),
    ]
