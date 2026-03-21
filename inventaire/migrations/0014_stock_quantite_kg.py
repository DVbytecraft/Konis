"""
Migration non-destructive : ajout de quantite_kg sur Stock.
Données existantes → quantite_kg=0 (pas de sacs convertis avant cette version).
"""
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0013_cash_credit_collecte_fournisseur"),
    ]

    operations = [
        migrations.AddField(
            model_name="stock",
            name="quantite_kg",
            field=models.DecimalField(
                default=Decimal("0"),
                decimal_places=3,
                max_digits=12,
                verbose_name="Kg supplémentaires (sacs convertis)",
                help_text="Kg issus de la conversion de sacs entiers. 0 si aucune conversion.",
            ),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(
                condition=models.Q(quantite_kg__gte=0),
                name="stock_quantite_kg_positive",
            ),
        ),
    ]
