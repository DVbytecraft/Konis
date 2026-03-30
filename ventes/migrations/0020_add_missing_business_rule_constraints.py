from django.db import migrations


class Migration(migrations.Migration):
    """
    Remplace l'ajout des CheckConstraints ticket_type_mouture_requis_si_mouture
    et ticket_cash_plus_credit_egal_total par des suppressions sécurisées (IF EXISTS).

    Raison : des tickets historiques en production ne satisfont pas ces contraintes
    (type_mouture NULL sur d'anciens tickets mouture, ou montant_cash/montant_credit
    à 0 par défaut avant que ces champs existent).
    La validation est maintenue au niveau du service (vente_boutique).
    """

    dependencies = [
        ("ventes", "0019_alter_lignevente_unite"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE ventes_ticket DROP CONSTRAINT IF EXISTS ticket_type_mouture_requis_si_mouture;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ventes_ticket DROP CONSTRAINT IF EXISTS ticket_cash_plus_credit_egal_total;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
