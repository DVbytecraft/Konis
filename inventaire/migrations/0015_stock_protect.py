"""
C1 — Sécurité : Stock.produit et Stock.lieu passent de CASCADE à PROTECT.

Avant : supprimer un Produit ou un Lieu effaçait silencieusement tout le stock
associé, entraînant une perte d'historique financier irréversible.

Après : toute tentative de suppression d'un Produit ou d'un Lieu ayant du stock
lève une IntegrityError (Django PROTECT), forçant un nettoyage préalable explicite.
"""
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0014_stock_quantite_kg"),
        ("produits",   "0001_initial"),
        ("core",       "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stock",
            name="produit",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stocks",
                to="produits.produit",
            ),
        ),
        migrations.AlterField(
            model_name="stock",
            name="lieu",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stocks",
                to="core.lieu",
            ),
        ),
    ]
