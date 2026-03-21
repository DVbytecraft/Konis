"""
Data migration : backfill des tickets existants.
Tous les tickets créés avant l'ajout de type_vente sont de type 'cash'.
  type_vente     = 'cash'
  montant_cash   = montant_total  (tous étaient encaissés intégralement)
  montant_credit = 0              (déjà le défaut, mais explicite)
"""
from django.db import migrations
from django.db.models import F


def backfill_type_vente(apps, schema_editor):
    Ticket = apps.get_model("ventes", "Ticket")
    # Tous les tickets sans type_vente explicite → cash
    Ticket.objects.filter(type_vente="").update(type_vente="cash")
    # montant_cash = montant_total pour tous les tickets cash avec montant_cash encore à 0
    Ticket.objects.filter(type_vente="cash", montant_cash=0).update(
        montant_cash=F("montant_total"),
        montant_credit=0,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ventes", "0014_cash_credit_collecte_fournisseur"),
    ]

    operations = [
        migrations.RunPython(backfill_type_vente, noop),
    ]
