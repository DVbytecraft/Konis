"""
Migration : ajout du type de lieu MPSL et du rôle utilisateur MPSL.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_lieu_mouture_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lieu",
            name="type_lieu",
            field=models.CharField(
                choices=[
                    ("usine", "Usine"),
                    ("magasin", "Magasin"),
                    ("mpsl", "MPSL"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="customuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("comptable", "Comptable"),
                    ("usine", "Usine"),
                    ("boutique", "Boutique"),
                    ("mpsl", "MPSL"),
                ],
                db_index=True,
                default="boutique",
                max_length=20,
            ),
        ),
    ]
