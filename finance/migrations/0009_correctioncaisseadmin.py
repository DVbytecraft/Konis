from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_creancier_statut_and_more"),
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CorrectionCaisseAdmin",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("montant", models.DecimalField(decimal_places=2, max_digits=14, help_text="Positif = ajout, négatif = retrait.")),
                ("motif", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lieu",
                    models.ForeignKey(
                        limit_choices_to={"type_lieu": "magasin"},
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="corrections_caisse_admin",
                        to="core.lieu",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Correction caisse admin",
                "verbose_name_plural": "Corrections caisse admin",
                "ordering": ["-created_at"],
            },
        ),
    ]
