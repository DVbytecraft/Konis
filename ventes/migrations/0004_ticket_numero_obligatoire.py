# Generated for KONIS V0 - Ticket.numero obligatoire, format KONIS-CODE-YYYYMMDD-SEQ

from django.db import migrations, models
from django.db.models import Q


def backfill_numero(apps, schema_editor):
    """Attribue un numéro aux tickets existants sans numéro."""
    Ticket = apps.get_model("ventes", "Ticket")
    Lieu = apps.get_model("core", "Lieu")

    qs = Ticket.objects.filter(Q(numero__isnull=True) | Q(numero="")).order_by("lieu", "date")
    seen = {}  # (lieu_id, date) -> last_seq
    for ticket in qs:
        lieu = Lieu.objects.get(pk=ticket.lieu_id)
        code = (getattr(lieu, "code", "") or "").strip().upper() or f"L{lieu.id}"
        code = "".join(c for c in code if c.isalnum())[:10] or f"L{lieu.id}"
        today = ticket.date.date() if hasattr(ticket.date, "date") else ticket.date
        key = (ticket.lieu_id, today)
        seq = seen.get(key, 0) + 1
        seen[key] = seq
        ticket.numero = f"KONIS-{code}-{today:%Y%m%d}-{seq:06d}"
        ticket.save(update_fields=["numero"])


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0003_ticket_unique_ticket_lieu_numero"),
        ("core", "0002_lieu_code"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="ticket",
            name="unique_ticket_lieu_numero",
        ),
        migrations.RunPython(backfill_numero, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ticket",
            name="numero",
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name="ticket",
            constraint=models.UniqueConstraint(fields=("lieu", "numero"), name="unique_ticket_lieu_numero"),
        ),
    ]
