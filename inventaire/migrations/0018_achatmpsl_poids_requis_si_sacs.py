from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0017_achatmpsl_poids_par_sac"),
    ]

    operations = [
        # Règle : si unite='sacs', poids_par_sac doit être renseigné
        migrations.AddConstraint(
            model_name="achatmpsl",
            constraint=models.CheckConstraint(
                condition=~models.Q(unite="sacs") | models.Q(poids_par_sac__isnull=False),
                name="achatmpsl_poids_requis_si_sacs",
            ),
        ),
    ]
