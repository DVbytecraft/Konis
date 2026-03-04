# Generated manually for KONIS V0 - unicité ticket (lieu, numero)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventes', '0002_ticket_ventes_tick_lieu_id_193297_idx_and_more'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.UniqueConstraint(
                condition=models.Q(numero__isnull=False) & ~models.Q(numero=""),
                fields=("lieu", "numero"),
                name="unique_ticket_lieu_numero",
            ),
        ),
    ]
