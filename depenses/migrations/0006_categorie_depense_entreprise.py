from django.db import migrations, models


def set_categorie_depense_entreprise(apps, schema_editor):
    Entreprise = apps.get_model("core", "Entreprise")
    CategorieDepense = apps.get_model("depenses", "CategorieDepense")
    ent = Entreprise.objects.order_by("id").first()
    if ent is None:
        return
    CategorieDepense.objects.filter(entreprise__isnull=True).update(entreprise=ent)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_audit_final_constraints"),
        ("depenses", "0005_audit_hardening"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoriedepense",
            name="entreprise",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.PROTECT,
                related_name="categories_depenses",
                to="core.entreprise",
            ),
        ),
        migrations.RunPython(set_categorie_depense_entreprise, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="categoriedepense",
            name="entreprise",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="categories_depenses",
                to="core.entreprise",
            ),
        ),
        migrations.AddIndex(
            model_name="categoriedepense",
            index=models.Index(fields=["entreprise", "nom"], name="depenses_ca_entrep_5c3c2b_idx"),
        ),
    ]
