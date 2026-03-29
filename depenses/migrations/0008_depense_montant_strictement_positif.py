from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("depenses", "0007_depense_lieu_optional_entreprise"),
    ]

    operations = [
        # Remplace depense_montant_positive (>= 0) par > 0
        # Une dépense de 0 FCFA n'a pas de sens métier.
        migrations.RemoveConstraint(
            model_name="depense",
            name="depense_montant_positive",
        ),
        migrations.AddConstraint(
            model_name="depense",
            constraint=models.CheckConstraint(
                condition=models.Q(montant__gt=0),
                name="depense_montant_strictement_positif",
            ),
        ),
    ]
