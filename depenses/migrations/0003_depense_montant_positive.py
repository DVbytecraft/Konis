# Generated for KONIS V0 - Depense montant >= 0

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("depenses", "0002_depense_depenses_de_lieu_id_3d2e1c_idx_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="depense",
            constraint=models.CheckConstraint(condition=models.Q(("montant__gte", 0)), name="depense_montant_positive"),
        ),
    ]
