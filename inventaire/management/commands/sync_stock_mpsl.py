"""
Synchronise le stock MPSL depuis les AchatMPSL existants.

Pourquoi cette commande existe :
    Avant le commit qui a ajouté la mise à jour stock dans enregistrer_achat_mpsl(),
    les achats MPSL étaient purement comptables (NE modifie PAS le stock).
    Les achats créés avant cette correction n'ont donc aucun enregistrement Stock.

Calcul :
    Pour chaque (lieu MPSL, produit) :
        sacs attendus = SUM(achats sacs) - SUM(sorties sacs estimées)
        kg attendus   = SUM(achats kg) + SUM(achats tonnes × 1000) - SUM(sorties kg estimées)

    Les sorties viennent des MouvementStock liés aux Transferts depuis le lieu MPSL.
    MouvementStock n'ayant pas de champ unité, on utilise l'unité native du produit
    (sac → sorties en sacs, kg → sorties en kg). Cela est correct dans le cas général.

Usage :
    python manage.py sync_stock_mpsl               # Dry-run : affiche sans modifier
    python manage.py sync_stock_mpsl --commit       # Applique les modifications
    python manage.py sync_stock_mpsl --lieu=<id>    # Limite à un lieu MPSL
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Sum

from core.models import Lieu
from inventaire.models import AchatMPSL, MouvementStock, Stock, Transfert
from produits.models import Produit


def _to_decimal(val) -> Decimal:
    return Decimal(str(val)) if val is not None else Decimal("0")


class Command(BaseCommand):
    help = "Synchronise le stock MPSL depuis les AchatMPSL (resync données historiques)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            default=False,
            help="Applique réellement les modifications. Sans ce flag : dry-run.",
        )
        parser.add_argument(
            "--lieu",
            type=int,
            default=None,
            help="Restreint la resync à un seul lieu MPSL (pk).",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        lieu_filter = options["lieu"]

        if not commit:
            self.stdout.write(self.style.WARNING(
                "=== DRY-RUN (aucune modification) — relancer avec --commit pour appliquer ==="
            ))

        # ── 1. Sélectionner les lieux MPSL concernés ──────────────────────────
        lieux_qs = Lieu.objects.filter(type_lieu=Lieu.TYPE_MPSL).select_related("entreprise")
        if lieu_filter:
            lieux_qs = lieux_qs.filter(pk=lieu_filter)

        if not lieux_qs.exists():
            self.stdout.write(self.style.ERROR("Aucun lieu MPSL trouvé."))
            return

        total_crees = 0
        total_maj = 0
        total_inchanges = 0

        for lieu in lieux_qs:
            self.stdout.write(f"\n── Lieu : {lieu.nom} (#{lieu.pk}, {lieu.entreprise})")

            # ── 2. Identifier tous les produits achetés sur ce lieu ───────────
            produit_noms = (
                AchatMPSL.objects
                .filter(lieu=lieu)
                .values_list("produit_nom", flat=True)
                .distinct()
            )

            if not produit_noms:
                self.stdout.write("   Aucun achat MPSL enregistré.")
                continue

            for nom in produit_noms:
                # ── 3. Trouver le Produit correspondant (FK) ──────────────────
                produit = Produit.objects.filter(
                    nom__iexact=nom,
                    entreprise_id=lieu.entreprise_id,
                ).first()

                if produit is None:
                    self.stdout.write(self.style.WARNING(
                        f"   ⚠ Produit '{nom}' introuvable dans le catalogue — ignoré."
                    ))
                    continue

                # ── 4. Total entrant (achats) ─────────────────────────────────
                achats_qs = AchatMPSL.objects.filter(lieu=lieu, produit_nom__iexact=nom)

                total_sac_in = _to_decimal(
                    achats_qs.filter(unite__in=("sac", "sacs"))
                    .aggregate(s=Sum("quantite"))["s"]
                )
                total_kg_in = _to_decimal(
                    achats_qs.filter(unite="kg")
                    .aggregate(s=Sum("quantite"))["s"]
                )
                total_tonne_in = _to_decimal(
                    achats_qs.filter(unite__in=("tonne", "tonnes"))
                    .aggregate(s=Sum("quantite"))["s"]
                )
                total_kg_in += total_tonne_in * Decimal("1000")

                # ── 5. Total sortant (transferts depuis ce lieu MPSL) ─────────
                # MouvementStock n'a pas de champ unité : on utilise l'unité native
                # du produit comme approximation (sac → sorties sacs, kg → sorties kg).
                mouvements_out_qs = MouvementStock.objects.filter(
                    produit=produit,
                    transfert__from_lieu=lieu,
                )
                total_out = _to_decimal(
                    mouvements_out_qs.aggregate(s=Sum("quantite"))["s"]
                )

                produit_unite = (produit.unite or "kg").strip().lower()
                if produit_unite in ("sac", "sacs"):
                    sac_out = total_out
                    kg_out = Decimal("0")
                else:
                    sac_out = Decimal("0")
                    kg_out = total_out

                # ── 6. Stock net attendu ──────────────────────────────────────
                expected_sac = max(Decimal("0"), total_sac_in - sac_out)
                expected_kg  = max(Decimal("0"), total_kg_in  - kg_out)

                # ── 7. Comparer avec l'état actuel ────────────────────────────
                stock = Stock.objects.filter(produit=produit, lieu=lieu).first()
                current_sac = _to_decimal(stock.quantite)    if stock else Decimal("0")
                current_kg  = _to_decimal(stock.quantite_kg) if stock else Decimal("0")

                if current_sac == expected_sac and current_kg == expected_kg:
                    total_inchanges += 1
                    self.stdout.write(
                        f"   = {produit.nom} : déjà à jour "
                        f"(sacs={current_sac}, kg={current_kg})"
                    )
                    continue

                action = "CRÉE" if not stock else "MIS À JOUR"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   {action} {produit.nom} : "
                        f"sacs {current_sac} → {expected_sac} | "
                        f"kg {current_kg} → {expected_kg}"
                    )
                    if commit else
                    f"   [DRY] {action} {produit.nom} : "
                    f"sacs {current_sac} → {expected_sac} | "
                    f"kg {current_kg} → {expected_kg}"
                )

                if commit:
                    with transaction.atomic():
                        if stock is None:
                            Stock.objects.create(
                                produit=produit,
                                lieu=lieu,
                                quantite=expected_sac,
                                quantite_kg=expected_kg,
                            )
                            total_crees += 1
                        else:
                            # SELECT FOR UPDATE pour éviter race condition
                            stock = Stock.objects.select_for_update().get(pk=stock.pk)
                            stock.quantite    = expected_sac
                            stock.quantite_kg = expected_kg
                            stock.save(update_fields=["quantite", "quantite_kg", "updated_at"])
                            total_maj += 1
                else:
                    if stock is None:
                        total_crees += 1
                    else:
                        total_maj += 1

        # ── Résumé ────────────────────────────────────────────────────────────
        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Terminé : {total_crees} créés, {total_maj} mis à jour, "
                f"{total_inchanges} inchangés."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"DRY-RUN terminé : {total_crees} à créer, {total_maj} à mettre à jour, "
                f"{total_inchanges} inchangés. Relancer avec --commit pour appliquer."
            ))
