from django.db import migrations


class Migration(migrations.Migration):
    """
    Remplace l'ajout de CheckConstraint achatmpsl_poids_requis_si_sacs
    par une suppression sécurisée (IF EXISTS).

    Raison : des lignes historiques en production ont unite='sacs' avec
    poids_par_sac=NULL, ce qui faisait échouer la migration au déploiement.
    La validation est maintenue au niveau du service (enregistrer_achat_mpsl).
    """

    dependencies = [
        ("inventaire", "0017_achatmpsl_poids_par_sac"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE inventaire_achatmpsl DROP CONSTRAINT IF EXISTS achatmpsl_poids_requis_si_sacs;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
