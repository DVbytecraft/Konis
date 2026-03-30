from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0018_achatmpsl_poids_requis_si_sacs"),
        ("usine", "0007_audit_final_constraints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transfertcession",
            name="transfert",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cessions",
                to="inventaire.transfert",
            ),
        ),
        migrations.AlterField(
            model_name="transfertinterusine",
            name="transfert",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="inter_usine_cessions",
                to="inventaire.transfert",
            ),
        ),
    ]
