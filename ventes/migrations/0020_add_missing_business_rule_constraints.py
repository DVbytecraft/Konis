from django.db import migrations, models
from django.db.models import F


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0019_alter_lignevente_unite"),
    ]

    operations = [
        # Règle : si mouture=True, type_mouture doit être renseigné
        migrations.AddConstraint(
            model_name="ticket",
            constraint=models.CheckConstraint(
                condition=models.Q(mouture=False) | models.Q(type_mouture__isnull=False),
                name="ticket_type_mouture_requis_si_mouture",
            ),
        ),
        # Règle : montant_cash + montant_credit = montant_total
        migrations.AddConstraint(
            model_name="ticket",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    montant_total=models.F("montant_cash") + models.F("montant_credit")
                ),
                name="ticket_cash_plus_credit_egal_total",
            ),
        ),
    ]
