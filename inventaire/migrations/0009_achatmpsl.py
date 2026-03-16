"""
Migration : création du modèle AchatMPSL (achat avec impact stock au dépôt MPSL).
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_add_mpsl"),
        ("inventaire", "0008_alter_stock_options"),
        ("produits", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AchatMPSL",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantite", models.DecimalField(decimal_places=2, max_digits=12)),
                ("unite", models.CharField(
                    choices=[("sacs", "Sacs"), ("kg", "Kilogrammes"), ("tonnes", "Tonnes")],
                    default="sacs",
                    max_length=10,
                )),
                ("prix_unitaire", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("prix_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("notes", models.TextField(blank=True, default="")),
                ("date", models.DateTimeField(auto_now_add=True)),
                ("lieu", models.ForeignKey(
                    limit_choices_to={"type_lieu": "mpsl"},
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="achats_mpsl",
                    to="core.lieu",
                )),
                ("produit", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="achats_mpsl",
                    to="produits.produit",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="achats_mpsl_crees",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Achat MPSL",
                "verbose_name_plural": "Achats MPSL",
                "ordering": ["-date"],
            },
        ),
        migrations.AddConstraint(
            model_name="achatmpsl",
            constraint=models.CheckConstraint(
                condition=models.Q(quantite__gt=0),
                name="achatmpsl_quantite_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="achatmpsl",
            constraint=models.CheckConstraint(
                condition=models.Q(prix_unitaire__gte=0),
                name="achatmpsl_prix_unitaire_positif",
            ),
        ),
        migrations.AddConstraint(
            model_name="achatmpsl",
            constraint=models.CheckConstraint(
                condition=models.Q(prix_total__gte=0),
                name="achatmpsl_prix_total_positif",
            ),
        ),
        migrations.AddIndex(
            model_name="achatmpsl",
            index=models.Index(fields=["lieu", "date"], name="inventaire__lieu_id_achatmpsl_idx"),
        ),
        migrations.AddIndex(
            model_name="achatmpsl",
            index=models.Index(fields=["produit", "lieu"], name="inventaire__produit_lieu_achatmpsl_idx"),
        ),
    ]
