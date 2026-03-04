"""
Migration 0006 : Simplification AchatUsine.
- Supprime la FK produit (remplacée par produit_nom CharField)
- Ajoute : produit_nom, unite, prix_unitaire, prix_total, notes, created_by
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0005_remove_transfert_created_at_remove_achatusine_created_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Ajouter les nouveaux champs (avec defaults pour les non-null)
        migrations.AddField(
            model_name="achatusine",
            name="produit_nom",
            field=models.CharField(default="", max_length=255, verbose_name="Produit acheté"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="achatusine",
            name="unite",
            field=models.CharField(
                choices=[("sacs", "Sacs"), ("kg", "Kilogrammes"), ("tonnes", "Tonnes")],
                default="sacs",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="achatusine",
            name="prix_unitaire",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="achatusine",
            name="prix_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="achatusine",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="achatusine",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="achats_usine_crees",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 2. Supprimer la FK produit
        migrations.RemoveField(
            model_name="achatusine",
            name="produit",
        ),
        # 3. Mettre à jour les contraintes
        migrations.RemoveConstraint(
            model_name="achatusine",
            name="achatusine_quantite_positive",
        ),
        migrations.AddConstraint(
            model_name="achatusine",
            constraint=models.CheckConstraint(
                condition=models.Q(quantite__gt=0),
                name="achatusine_quantite_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="achatusine",
            constraint=models.CheckConstraint(
                condition=models.Q(prix_unitaire__gte=0),
                name="achatusine_prix_unitaire_positif",
            ),
        ),
        migrations.AddConstraint(
            model_name="achatusine",
            constraint=models.CheckConstraint(
                condition=models.Q(prix_total__gte=0),
                name="achatusine_prix_total_positif",
            ),
        ),
        # 4. Ajouter index lieu/date
        migrations.AddIndex(
            model_name="achatusine",
            index=models.Index(fields=["lieu", "date"], name="inventaire_achatusine_lieu_date_idx"),
        ),
    ]
