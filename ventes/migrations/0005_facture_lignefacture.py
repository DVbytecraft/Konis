from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("produits", "0002_produit_category"),
        ("core", "0004_lieu_adresse_lieu_is_active"),
        ("ventes", "0004_ticket_numero_obligatoire"),
    ]

    operations = [
        migrations.CreateModel(
            name="Facture",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(max_length=50)),
                ("date", models.DateTimeField(auto_now_add=True)),
                ("source_role", models.CharField(choices=[("admin", "Admin"), ("comptable", "Comptable"), ("usine", "Usine"), ("boutique", "Boutique")], max_length=20)),
                ("client_nom", models.CharField(blank=True, default="", max_length=255)),
                ("client_contact", models.CharField(blank=True, default="", max_length=255)),
                ("notes", models.TextField(blank=True, default="")),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="factures_creees", to=settings.AUTH_USER_MODEL)),
                ("lieu", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="factures", to="core.lieu")),
            ],
            options={
                "verbose_name": "Facture",
                "verbose_name_plural": "Factures",
                "ordering": ["-date"],
            },
        ),
        migrations.CreateModel(
            name="LigneFacture",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=255)),
                ("quantite", models.DecimalField(decimal_places=2, max_digits=12)),
                ("prix_unitaire", models.DecimalField(decimal_places=2, max_digits=12)),
                ("facture", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lignes", to="ventes.facture")),
                ("produit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="lignes_facture", to="produits.produit")),
            ],
            options={
                "verbose_name": "Ligne de facture",
                "verbose_name_plural": "Lignes de facture",
            },
        ),
        migrations.AddIndex(
            model_name="facture",
            index=models.Index(fields=["lieu", "date"], name="ventes_factu_lieu_id_a42f9b_idx"),
        ),
        migrations.AddIndex(
            model_name="facture",
            index=models.Index(fields=["date"], name="ventes_factu_date_8c8aa2_idx"),
        ),
        migrations.AddConstraint(
            model_name="facture",
            constraint=models.UniqueConstraint(fields=("lieu", "numero"), name="unique_facture_lieu_numero"),
        ),
    ]
