from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_audit_final_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="entreprise",
            name="nif",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="NIF"),
        ),
        migrations.AddField(
            model_name="entreprise",
            name="quitus_fiscal",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Quitus fiscal"),
        ),
    ]
