from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0016_ticket_nombre_sacs_poids_par_sac"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="type_mouture",
            field=models.CharField(
                blank=True,
                choices=[
                    ("client_externe", "Client externe"),
                    ("production_interne", "Production interne"),
                ],
                db_index=True,
                help_text="client_externe = revenu comptabilisé ; production_interne = usage interne, hors CA.",
                max_length=20,
                null=True,
                verbose_name="Type de mouture",
            ),
        ),
        # Backfill: all existing mouture tickets → client_externe
        migrations.RunSQL(
            sql="""
                UPDATE ventes_ticket
                SET type_mouture = 'client_externe'
                WHERE mouture = TRUE AND type_mouture IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
