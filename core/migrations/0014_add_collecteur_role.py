from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_audit_final_constraints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("supreme_admin", "Supreme Admin"),
                    ("admin",         "Admin"),
                    ("daf",           "DAF"),
                    ("comptable",     "Comptable"),
                    ("usine",         "Usine"),
                    ("boutique",      "Boutique"),
                    ("mpsl",          "MPSL"),
                    ("collecteur",    "Collecteur"),
                ],
                db_index=True,
                default="boutique",
                max_length=20,
            ),
        ),
    ]
