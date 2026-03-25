"""
Migration 0016 — AchatMPSL.journal_payable : OneToOneField → ForeignKey

Pourquoi : le batch d'achats MPSL crée un seul JournalPayable partagé entre
plusieurs AchatMPSL (un par produit). La contrainte OneToOneField empêchait de
lier tous les achats au même journal.

Impact : aucune donnée perdue — la contrainte UNIQUE de la colonne FK est
supprimée, les valeurs existantes restent intactes.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0015_stock_protect"),
        ("finance", "0001_finance_app_et_nouveaux_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="achatmpsl",
            name="journal_payable",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Journal de dette fournisseur auto-créé si crédit ou partiel. "
                    "Plusieurs achats d'un même bon de commande partagent le même journal."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="achats_mpsl",
                to="finance.journalpayable",
            ),
        ),
    ]
