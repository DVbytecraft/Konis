"""
Migration 0003 : Simplification des modèles usine.
- Supprime CompositionLot (table entière)
- Supprime ReceptionMatierePremiere (table entière)
- Simplifie LotProduction : supprime composition JSON, cout_total; renomme quantite_produite → quantite_sacs; ajoute poids, unite_poids
- Simplifie TransfertCession : renomme quantite → quantite_sacs, prix_cession_unitaire → prix_par_sac; ajoute poids_total
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usine", "0002_lotproduction_composition_and_reception_mp"),
        ("inventaire", "0005_remove_transfert_created_at_remove_achatusine_created_at"),
    ]

    operations = [
        # ── Supprimer CompositionLot ──────────────────────────────────────────
        migrations.DeleteModel(
            name="CompositionLot",
        ),

        # ── Supprimer ReceptionMatierePremiere ───────────────────────────────
        migrations.DeleteModel(
            name="ReceptionMatierePremiere",
        ),

        # ── LotProduction : supprimer les champs obsolètes ────────────────────
        migrations.RemoveConstraint(
            model_name="lotproduction",
            name="lot_quantite_positive",
        ),
        migrations.RemoveConstraint(
            model_name="lotproduction",
            name="lot_cout_non_negatif",
        ),
        migrations.RemoveField(
            model_name="lotproduction",
            name="composition",
        ),
        migrations.RemoveField(
            model_name="lotproduction",
            name="cout_total",
        ),
        # Renommer quantite_produite → quantite_sacs
        migrations.RenameField(
            model_name="lotproduction",
            old_name="quantite_produite",
            new_name="quantite_sacs",
        ),
        # Ajouter poids et unite_poids
        migrations.AddField(
            model_name="lotproduction",
            name="poids",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Poids total"),
        ),
        migrations.AddField(
            model_name="lotproduction",
            name="unite_poids",
            field=models.CharField(
                choices=[("kg", "Kilogrammes"), ("tonnes", "Tonnes")],
                default="kg",
                max_length=10,
                verbose_name="Unité de poids",
            ),
        ),
        # Nouvelles contraintes LotProduction
        migrations.AddConstraint(
            model_name="lotproduction",
            constraint=models.CheckConstraint(
                condition=models.Q(quantite_sacs__gt=0),
                name="lot_quantite_sacs_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="lotproduction",
            constraint=models.CheckConstraint(
                condition=models.Q(poids__gte=0),
                name="lot_poids_non_negatif",
            ),
        ),

        # ── TransfertCession : mise à jour ────────────────────────────────────
        migrations.RemoveConstraint(
            model_name="transfertcession",
            name="cession_quantite_positive",
        ),
        migrations.RemoveConstraint(
            model_name="transfertcession",
            name="cession_prix_non_negatif",
        ),
        # Renommer quantite → quantite_sacs
        migrations.RenameField(
            model_name="transfertcession",
            old_name="quantite",
            new_name="quantite_sacs",
        ),
        # Renommer prix_cession_unitaire → prix_par_sac
        migrations.RenameField(
            model_name="transfertcession",
            old_name="prix_cession_unitaire",
            new_name="prix_par_sac",
        ),
        # Ajouter poids_total
        migrations.AddField(
            model_name="transfertcession",
            name="poids_total",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12, verbose_name="Poids total transféré"
            ),
        ),
        # Nouvelles contraintes TransfertCession
        migrations.AddConstraint(
            model_name="transfertcession",
            constraint=models.CheckConstraint(
                condition=models.Q(quantite_sacs__gt=0),
                name="cession_quantite_sacs_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="transfertcession",
            constraint=models.CheckConstraint(
                condition=models.Q(prix_par_sac__gte=0),
                name="cession_prix_non_negatif",
            ),
        ),
        migrations.AddConstraint(
            model_name="transfertcession",
            constraint=models.CheckConstraint(
                condition=models.Q(poids_total__gte=0),
                name="cession_poids_non_negatif",
            ),
        ),
    ]
