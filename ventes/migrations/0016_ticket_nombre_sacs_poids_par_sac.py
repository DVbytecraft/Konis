from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0015_backfill_type_vente"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="nombre_sacs",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Nombre de sacs (saisie par sacs)",
                help_text="Renseigné uniquement si la saisie a été effectuée en mode 'par sacs'.",
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="poids_par_sac",
            field=models.DecimalField(
                blank=True,
                null=True,
                max_digits=10,
                decimal_places=3,
                verbose_name="Poids par sac (kg)",
                help_text="Poids unitaire du sac en kg (saisie par sacs).",
            ),
        ),
        migrations.AddConstraint(
            model_name="ticket",
            constraint=models.CheckConstraint(
                condition=Q(poids_par_sac__isnull=True) | Q(poids_par_sac__gt=0),
                name="ticket_poids_par_sac_positif",
            ),
        ),
    ]
