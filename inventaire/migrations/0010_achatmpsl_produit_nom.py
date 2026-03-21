"""
Migration : remplace AchatMPSL.produit (FK) par produit_nom (CharField).
L'enregistrement d'achat MPSL devient purement comptable (comme AchatUsine),
sans impact sur le stock inventaire.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0009_achatmpsl"),
        ("produits", "0001_initial"),
    ]

    operations = [
        # Étape 1 : supprimer l'index sur (produit, lieu)
        # SQLite peut ne pas avoir l'index (ex: DB de dev partielle) -> DROP IF EXISTS
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="DROP INDEX IF EXISTS achatmpsl_produit_lieu_idx;",
                    reverse_sql="SELECT 1;",
                )
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="achatmpsl",
                    name="achatmpsl_produit_lieu_idx",
                ),
            ],
        ),
        # Étape 2 : ajouter produit_nom avec une valeur par défaut temporaire
        migrations.AddField(
            model_name="achatmpsl",
            name="produit_nom",
            field=models.CharField(
                max_length=255,
                verbose_name="Produit acheté",
                default="",
            ),
            preserve_default=False,
        ),
        # Étape 3 : supprimer la FK produit
        migrations.RemoveField(
            model_name="achatmpsl",
            name="produit",
        ),
    ]
