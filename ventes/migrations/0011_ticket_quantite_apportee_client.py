from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0010_ticket_idempotency_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="quantite_apportee_client",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                default=Decimal("0"),
                help_text="Toujours stocké en kg après normalisation.",
                max_digits=12,
                verbose_name="Quantité grain apportée par le client (kg, normalisé)",
            ),
        ),
    ]
