from decimal import Decimal

from django.core.management.base import BaseCommand

from inventaire.models import Stock, MouvementStock
from ventes.models import LigneVente
from finance.models import JournalCreance, JournalPayable


class Command(BaseCommand):
    help = "Vérifie la cohérence des stocks (sacs/kg) sans modifier la base."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Nombre max d'éléments affichés par type d'anomalie (défaut: 200).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        issues = {
            "stock_negatif": [],
            "poids_par_sac_manquant": [],
            "doublon_kg_quantite": [],
            "sac_fractionnaire": [],
            "ventes_incoherentes": [],
            "transferts_incoherents": [],
            "creances_incoherentes": [],
            "payables_incoherents": [],
        }

        qs = Stock.objects.select_related("produit", "lieu").all()
        for s in qs:
            q_sac = s.quantite or Decimal("0")
            q_kg = s.quantite_kg or Decimal("0")
            pps = getattr(s.produit, "poids_par_sac", None)
            unite = (s.produit.unite or "").strip().lower()

            if q_sac < 0 or q_kg < 0:
                issues["stock_negatif"].append(s)

            # Produit en sac : poids_par_sac requis si stock présent
            if unite in ("sac", "sacs") and (q_sac > 0 or q_kg > 0) and not pps:
                issues["poids_par_sac_manquant"].append(s)

            # Produit en kg (pas de sacs) : quantite_kg + quantite remplis -> doublon potentiel
            if unite == "kg" and not pps and q_sac > 0 and q_kg > 0:
                issues["doublon_kg_quantite"].append(s)

            # Sacs fractionnaires (devrait être entier)
            if unite in ("sac", "sacs") and q_sac % 1 != 0:
                issues["sac_fractionnaire"].append(s)

        # Vérif ventes : unité sac sans poids_par_sac, ou quantité invalide
        for lv in LigneVente.objects.select_related("produit").all():
            u = (lv.unite or lv.produit.unite or "").strip().lower()
            pps = getattr(lv.produit, "poids_par_sac", None)
            if lv.quantite <= 0:
                issues["ventes_incoherentes"].append(lv)
                continue
            if u in ("sac", "sacs") and not pps:
                issues["ventes_incoherentes"].append(lv)

        # Vérif transferts : quantité invalide ou lieux incohérents
        for mv in MouvementStock.objects.select_related("transfert", "produit").all():
            if mv.quantite <= 0:
                issues["transferts_incoherents"].append(mv)
                continue
            if mv.transfert and mv.transfert.from_lieu_id == mv.transfert.to_lieu_id:
                issues["transferts_incoherents"].append(mv)

        # Vérif cohérence créances/payables vs paiements
        for j in JournalCreance.objects.prefetch_related("paiements").all():
            total_paiements = sum((p.montant for p in j.paiements.all()), Decimal("0"))
            if total_paiements != (j.montant_paye or Decimal("0")):
                issues["creances_incoherentes"].append(j)
                continue
            if j.montant_paye > j.montant_initial:
                issues["creances_incoherentes"].append(j)
                continue
            if j.montant_restant != (j.montant_initial - j.montant_paye):
                issues["creances_incoherentes"].append(j)

        for j in JournalPayable.objects.prefetch_related("paiements").all():
            total_paiements = sum((p.montant for p in j.paiements.all()), Decimal("0"))
            if total_paiements != (j.montant_paye or Decimal("0")):
                issues["payables_incoherents"].append(j)
                continue
            if j.montant_paye > j.montant_initial:
                issues["payables_incoherents"].append(j)
                continue
            if j.montant_restant != (j.montant_initial - j.montant_paye):
                issues["payables_incoherents"].append(j)

        total_issues = sum(len(v) for v in issues.values())
        self.stdout.write(self.style.WARNING(f"Anomalies détectées: {total_issues}"))

        def _print_list(title, rows):
            self.stdout.write(self.style.WARNING(f"\n{title}: {len(rows)}"))
            for s in rows[:limit]:
                if hasattr(s, "lieu") and hasattr(s, "produit"):
                    self.stdout.write(
                        f"- Stock#{s.pk} | {s.lieu.nom} | {s.produit.nom} | "
                        f"unite={s.produit.unite} | q_sac={s.quantite} | q_kg={s.quantite_kg} | "
                        f"pps={s.produit.poids_par_sac}"
                    )
                elif hasattr(s, "produit"):
                    self.stdout.write(
                        f"- LigneVente#{s.pk} | {s.produit.nom} | unite={s.unite or s.produit.unite} | "
                        f"quantite={s.quantite}"
                    )
                elif hasattr(s, "transfert"):
                    self.stdout.write(
                        f"- Mouvement#{s.pk} | transfert={s.transfert_id} | quantite={s.quantite}"
                    )
                else:
                    self.stdout.write(f"- #{s.pk}")

        _print_list("Stock négatif", issues["stock_negatif"])
        _print_list("Poids par sac manquant", issues["poids_par_sac_manquant"])
        _print_list("Doublon kg/quantite", issues["doublon_kg_quantite"])
        _print_list("Sacs fractionnaires", issues["sac_fractionnaire"])
        _print_list("Ventes incohérentes", issues["ventes_incoherentes"])
        _print_list("Transferts incohérents", issues["transferts_incoherents"])
        _print_list("Créances incohérentes", issues["creances_incoherentes"])
        _print_list("Payables incohérents", issues["payables_incoherents"])

        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS("OK: aucun problème détecté."))
