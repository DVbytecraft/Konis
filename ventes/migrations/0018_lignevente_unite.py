from django.db import migrations, models


def backfill_lignevente_unite(apps, schema_editor):
    LigneVente = apps.get_model("ventes", "LigneVente")
    for lv in LigneVente.objects.select_related("produit").all():
        if not lv.unite:
            lv.unite = getattr(lv.produit, "unite", "") or ""
            lv.save(update_fields=["unite"])


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0017_ticket_type_mouture"),
    ]

    operations = [
        migrations.AddField(
            model_name="lignevente",
            name="unite",
            field=models.CharField(
                blank=True,
                default="",
                help_text="UnitÃ© de la ligne (ex. kg, sac).",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_lignevente_unite, migrations.RunPython.noop),
    ]
