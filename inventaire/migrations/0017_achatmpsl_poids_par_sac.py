"""
Migration 0017 — AchatMPSL.poids_par_sac

Ajoute la colonne poids_par_sac (DecimalField nullable) sur AchatMPSL.
Ce champ était manquant : le poids du sac était saisi au moment de l'achat
mais n'était enregistré que sur Produit.poids_par_sac, sans traçabilité
par achat. Désormais chaque achat en sacs stocke son propre poids_par_sac.

Impact données existantes : NULL pour tous les enregistrements antérieurs.
Le service utilise Produit.poids_par_sac comme fallback pour ces anciens achats.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0016_achatmpsl_journal_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="achatmpsl",
            name="poids_par_sac",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Poids d'un sac en kg. Renseigné si unite='sacs'. "
                          "Garantit la traçabilité et empêche les mélanges de poids.",
                max_digits=8,
                null=True,
                verbose_name="Poids par sac (kg)",
            ),
        ),
        migrations.AddConstraint(
            model_name="achatmpsl",
            constraint=models.CheckConstraint(
                condition=models.Q(poids_par_sac__isnull=True) | models.Q(poids_par_sac__gt=0),
                name="achatmpsl_poids_par_sac_positif",
            ),
        ),
    ]
