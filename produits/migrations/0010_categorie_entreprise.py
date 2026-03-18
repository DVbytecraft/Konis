from django.db import migrations, models


def set_categorie_entreprise(apps, schema_editor):
    Entreprise = apps.get_model("core", "Entreprise")
    Categorie = apps.get_model("produits", "Categorie")
    ent = Entreprise.objects.order_by("id").first()
    if ent is None:
        return
    Categorie.objects.filter(entreprise__isnull=True).update(entreprise=ent)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_audit_final_constraints"),
        ("produits", "0009_audit_final_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="categorie",
            name="entreprise",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.PROTECT,
                related_name="categories_produits",
                to="core.entreprise",
            ),
        ),
        migrations.RunPython(set_categorie_entreprise, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="categorie",
            name="entreprise",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="categories_produits",
                to="core.entreprise",
            ),
        ),
        migrations.AddIndex(
            model_name="categorie",
            index=models.Index(fields=["entreprise", "nom"], name="produits_ca_entrep_8f4f7e_idx"),
        ),
    ]
