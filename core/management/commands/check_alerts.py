"""
Commande de surveillance post-lancement KONIS.

Usage :
    python manage.py check_alerts
    python manage.py check_alerts --seuil-stock 5 --seuil-creances 500000

Détecte et logue (logger konis.alerts) :
  - Stocks boutique sous le seuil minimum (défaut : 2 sacs ou 2 kg)
  - Projets en dépassement budgétaire
  - Créances clients restantes > seuil (défaut : 100 000 FCFA par créance)
  - Collectes non déposées depuis > N jours (défaut : 3 jours)
  - Conversions sac→kg anormalement fréquentes (> seuil/jour, défaut : 20)
  - Tickets sans idempotency_key en base (mode STRICT activé → anomalie front)

Utilisation recommandée : cron toutes les heures en prod.
  0 * * * * /app/venv/bin/python /app/manage.py check_alerts >> /var/log/konis_alerts.log 2>&1
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

logger_alerts = logging.getLogger("konis.alerts")
logger_audit  = logging.getLogger("konis.audit")


def _persister_alerte(code: str, message: str, niveau: str = "warning", extra: dict = None, entreprise=None):
    """Persiste une alerte en base (AlerteLog) en plus du log."""
    from audit.models import AlerteLog
    AlerteLog.objects.create(
        code=code,
        niveau=niveau,
        message=message,
        extra=extra or {},
        entreprise=entreprise,
    )


class Command(BaseCommand):
    help = "Vérifie les indicateurs d'alerte post-lancement KONIS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seuil-stock",
            type=int,
            default=2,
            help="Seuil minimum de stock (sacs ou kg) avant alerte (défaut : 2).",
        )
        parser.add_argument(
            "--seuil-creances",
            type=int,
            default=100_000,
            help="Montant restant d'une créance déclenchant une alerte (défaut : 100 000 FCFA).",
        )
        parser.add_argument(
            "--jours-collectes",
            type=int,
            default=3,
            help="Nombre de jours sans dépôt bancaire avant alerte collecte (défaut : 3).",
        )
        parser.add_argument(
            "--seuil-conversions-jour",
            type=int,
            default=20,
            help="Nombre de conversions sac→kg/jour déclenchant une alerte (défaut : 20).",
        )

    def handle(self, *args, **options):
        seuil_stock         = options["seuil_stock"]
        seuil_creances      = Decimal(str(options["seuil_creances"]))
        jours_collectes     = options["jours_collectes"]
        seuil_conversions   = options["seuil_conversions_jour"]

        now = timezone.now()
        today = now.date()
        alertes = 0

        # ── 1. Stocks boutique sous le seuil ──────────────────────────────────
        from inventaire.models import Stock
        from core.models import Lieu
        from django.db.models import Q

        lieux_boutiques = Lieu.objects.filter(type_lieu=Lieu.TYPE_MAGASIN, is_active=True)
        for lieu in lieux_boutiques:
            stocks_bas = Stock.objects.filter(lieu=lieu).filter(
                Q(quantite__lt=seuil_stock, quantite__gt=0) |
                Q(quantite_kg__lt=seuil_stock, quantite_kg__gt=0)
            ).select_related("produit")
            for s in stocks_bas:
                msg = (
                    f"Stock bas — lieu={lieu.nom} produit={s.produit.nom} "
                    f"quantite={s.quantite} quantite_kg={s.quantite_kg} seuil={seuil_stock}"
                )
                logger_alerts.warning("STOCK_BAS %s", msg)
                _persister_alerte(
                    "STOCK_BAS", msg, "warning",
                    {"lieu": lieu.nom, "produit": s.produit.nom,
                     "quantite": str(s.quantite), "quantite_kg": str(s.quantite_kg),
                     "seuil": seuil_stock},
                    entreprise=lieu.entreprise,
                )
                alertes += 1

            # Stocks à zéro (complètement épuisés)
            stocks_zero = Stock.objects.filter(lieu=lieu, quantite=0, quantite_kg=0)
            if stocks_zero.exists():
                noms = ", ".join(
                    stocks_zero.select_related("produit").values_list("produit__nom", flat=True)[:5]
                )
                nb = stocks_zero.count()
                msg = f"Stock épuisé — lieu={lieu.nom} produits=[{noms}] nb={nb}"
                logger_alerts.warning("STOCK_ZERO %s", msg)
                _persister_alerte(
                    "STOCK_ZERO", msg, "warning",
                    {"lieu": lieu.nom, "produits": noms, "nb": nb},
                    entreprise=lieu.entreprise,
                )
                alertes += 1

        # ── 2. Projets en dépassement budgétaire ──────────────────────────────
        from finance.models import Projet, DepenseProjet, DepotProjet
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        from django.db.models.functions import Coalesce
        from django.db.models import Subquery, OuterRef, Value

        projets_actifs = Projet.objects.filter(statut="en_cours")
        projets_annotated = projets_actifs.annotate(
            _tot_depots=Coalesce(
                Subquery(
                    DepotProjet.objects.filter(projet=OuterRef("pk"))
                    .values("projet").annotate(_s=Sum("montant")).values("_s")
                ),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            _tot_depenses=Coalesce(
                Subquery(
                    DepenseProjet.objects.filter(projet=OuterRef("pk"))
                    .values("projet").annotate(_s=Sum("montant")).values("_s")
                ),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        for p in projets_annotated.filter(
            _tot_depenses__gt=F("budget_initial") + F("_tot_depots")
        ):
            depassement = p._tot_depenses - (p.budget_initial + p._tot_depots)
            msg = f"Dépassement budget — projet={p.nom} depassement={depassement} FCFA"
            logger_alerts.warning("PROJET_DEPASSEMENT %s", msg)
            _persister_alerte(
                "PROJET_DEPASSEMENT", msg, "warning",
                {"projet": p.nom, "depassement": str(depassement),
                 "budget": str(p.budget_initial), "depenses": str(p._tot_depenses)},
                entreprise=p.entreprise,
            )
            alertes += 1

        # ── 3. Créances restantes > seuil ─────────────────────────────────────
        from finance.models import JournalCreance
        creances_alertes = JournalCreance.objects.filter(statut="en_cours").extra(
            where=["(montant_initial - montant_paye) > %s"],
            params=[str(seuil_creances)],
        ).select_related("client", "lieu")
        for jc in creances_alertes:
            restant = jc.montant_initial - jc.montant_paye
            lieu_nom = jc.lieu.nom if jc.lieu else "N/A"
            msg = f"Créance élevée — client={jc.client.nom} lieu={lieu_nom} restant={restant} FCFA ref={jc.reference}"
            logger_alerts.warning("CREANCE_ELEVEE %s", msg)
            _persister_alerte(
                "CREANCE_ELEVEE", msg, "warning",
                {"client": jc.client.nom, "lieu": lieu_nom,
                 "restant": str(restant), "reference": jc.reference},
                entreprise=getattr(jc.lieu, "entreprise", None) if jc.lieu else None,
            )
            alertes += 1

        # ── 4. Collectes non déposées depuis > N jours ────────────────────────
        from finance.models import CollecteArgent
        seuil_date = now - timedelta(days=jours_collectes)
        collectes_en_attente = CollecteArgent.objects.filter(
            depot_banque__isnull=True,
            montant_pris__gt=0,
            created_at__lt=seuil_date,
        ).select_related("lieu")
        for c in collectes_en_attente:
            age_jours = (now - c.created_at).days
            msg = (
                f"Collecte non déposée — lieu={c.lieu.nom} date={c.date_collecte} "
                f"montant_pris={c.montant_pris} age={age_jours}j"
            )
            logger_alerts.warning("COLLECTE_NON_DEPOSEE %s", msg)
            _persister_alerte(
                "COLLECTE_NON_DEPOSEE", msg, "warning",
                {"lieu": c.lieu.nom, "date": str(c.date_collecte),
                 "montant_pris": str(c.montant_pris), "age_jours": age_jours},
                entreprise=c.lieu.entreprise,
            )
            alertes += 1

        # ── 5. Conversions sac→kg anormalement fréquentes ────────────────────
        from audit.models import AuditLog
        nb_conversions_today = AuditLog.objects.filter(
            action="conversion_sac_en_kg",
            created_at__date=today,
        ).count()
        if nb_conversions_today >= seuil_conversions:
            msg = (
                f"Conversions fréquentes — nb={nb_conversions_today} seuil={seuil_conversions} date={today} "
                "(vérifier si le stock est bien calibré en sacs/kg)"
            )
            logger_alerts.warning("CONVERSIONS_FREQUENTES %s", msg)
            _persister_alerte(
                "CONVERSIONS_FREQUENTES", msg, "warning",
                {"nb": nb_conversions_today, "seuil": seuil_conversions, "date": str(today)},
            )
            alertes += 1

        # ── 6. Tickets sans idempotency_key (anomalie front en mode STRICT) ───
        from django.conf import settings as django_settings
        if getattr(django_settings, "IDEMPOTENCY_STRICT_MODE", False):
            from ventes.models import Ticket
            tickets_sans_key = Ticket.objects.filter(
                idempotency_key__isnull=True,
                date__date=today,
            ).count()
            if tickets_sans_key > 0:
                msg = (
                    f"Tickets sans Idempotency-Key — nb={tickets_sans_key} date={today} "
                    "(STRICT_MODE=True — le front n'envoie pas le header Idempotency-Key)"
                )
                logger_alerts.error("TICKETS_SANS_IDEMPOTENCY_KEY %s", msg)
                _persister_alerte(
                    "TICKETS_SANS_IDEMPOTENCY_KEY", msg, "error",
                    {"nb": tickets_sans_key, "date": str(today)},
                )
                alertes += 1

        # ── Résumé ────────────────────────────────────────────────────────────
        if alertes == 0:
            logger_audit.info("check_alerts OK — aucune anomalie détectée date=%s", today)
            self.stdout.write(self.style.SUCCESS(f"[{today}] OK — aucune anomalie."))
        else:
            logger_alerts.warning(
                "check_alerts RESUME nb_alertes=%d date=%s", alertes, today
            )
            self.stdout.write(
                self.style.WARNING(f"[{today}] {alertes} alerte(s) — voir logs konis.alerts.")
            )
            self._notify(alertes, today)

    # ── Notifications Slack / Email ────────────────────────────────────────────

    def _notify(self, nb_alertes: int, today) -> None:
        """Lance les notifications Slack/email dans des threads séparés (non bloquants)."""
        import threading
        from django.conf import settings as django_settings

        texte = (
            f"[KONIS check_alerts] {nb_alertes} alerte(s) détectée(s) le {today}.\n"
            "Consultez les logs `konis.alerts` pour le détail."
        )

        threads = []

        slack_url = getattr(django_settings, "SLACK_ALERTS_WEBHOOK_URL", "")
        if slack_url:
            t = threading.Thread(
                target=self._send_slack, args=(slack_url, texte), daemon=True
            )
            threads.append(t)

        email_to = getattr(django_settings, "ALERTS_EMAIL_TO", "")
        if email_to:
            t = threading.Thread(
                target=self._send_email, args=(email_to, nb_alertes, today, texte), daemon=True
            )
            threads.append(t)

        for t in threads:
            t.start()

        # Attendre max 10 s au total pour que les threads terminent avant la fin du cron
        for t in threads:
            t.join(timeout=10)

    def _send_slack(self, webhook_url: str, texte: str) -> None:
        import json
        import urllib.error
        import urllib.request

        payload = json.dumps({"text": texte}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    logger_alerts.error("SLACK_NOTIFY_FAILED status=%d", resp.status)
        except urllib.error.URLError as exc:
            logger_alerts.error("SLACK_NOTIFY_ERROR err=%s", exc)

    def _send_email(self, email_to: str, nb_alertes: int, today, texte: str) -> None:
        from django.conf import settings as django_settings
        from django.core.mail import send_mail

        sujet = f"[KONIS] {nb_alertes} alerte(s) détectée(s) — {today}"
        from_email = getattr(django_settings, "DEFAULT_FROM_EMAIL", "noreply@konis.app")
        try:
            send_mail(
                subject=sujet,
                message=texte,
                from_email=from_email,
                recipient_list=[a.strip() for a in email_to.split(",") if a.strip()],
                fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger_alerts.error("EMAIL_NOTIFY_ERROR err=%s", exc)
