from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_auditlog_ip_address"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlerteLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(
                    db_index=True, max_length=64,
                    help_text="Ex : STOCK_BAS, PROJET_DEPASSEMENT, TICKETS_SANS_IDEMPOTENCY_KEY",
                )),
                ("niveau", models.CharField(
                    choices=[("info", "Info"), ("warning", "Warning"), ("error", "Error")],
                    default="warning", max_length=10,
                )),
                ("message", models.TextField()),
                ("extra", models.JSONField(blank=True, default=dict,
                                           help_text="Données structurées : lieu, produit, montant, etc.")),
                ("entreprise", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="alertes",
                    to="core.entreprise",
                    help_text="Entreprise concernée (null = alerte globale).",
                )),
                ("resolu", models.BooleanField(default=False,
                                               help_text="Marquer True une fois l'alerte traitée.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Alerte",
                "verbose_name_plural": "Alertes",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="alertelog",
            index=models.Index(fields=["code", "created_at"], name="audit_alerte_code_idx"),
        ),
        migrations.AddIndex(
            model_name="alertelog",
            index=models.Index(fields=["niveau", "resolu", "created_at"], name="audit_alerte_niveau_idx"),
        ),
        migrations.AddIndex(
            model_name="alertelog",
            index=models.Index(fields=["entreprise", "created_at"], name="audit_alerte_ent_idx"),
        ),
    ]
