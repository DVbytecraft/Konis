"""
Synchronise le stock MPSL depuis les AchatMPSL existants.

Pourquoi cette commande existe :
    Avant le commit qui a ajouté la mise à jour stock dans enregistrer_achat_mpsl(),
    les achats MPSL étaient purement comptables (NE modifie PAS le stock).
    Les achats créés avant cette correction n'ont donc aucun enregistrement Stock.

Périmètre :
    Tous les produits présents dans AchatMPSL OU déjà en stock au lieu MPSL.

Calcul par produit :
    initial    = SUM(achats sacs/kg/tonnes)
    transféré  = SUM(MouvementStock depuis ce lieu MPSL pour ce produit)
    restant    = MAX(0, initial - transféré)

    Règle sacs → kg :
        Pour un produit en sacs, quantite_kg vient uniquement de conversions sacs→kg,
        jamais d'achats directs en kg. Elle est préservée telle quelle.
        Pour un produit en kg/tonne, quantite_kg est recalculée depuis les achats.

    Note sur MouvementStock :
        Le modèle n'a pas de champ unité. On utilise l'unité native du produit
        comme approximation (sac → sorties en sacs, kg → sorties en kg).

Usage :
    python manage.py sync_stock_mpsl               # Dry-run : rapport sans modification
    python manage.py sync_stock_mpsl --commit       # Applique les corrections
    python manage.py sync_stock_mpsl --lieu=<pk>    # Limite à un lieu MPSL
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import Lieu
from inventaire.models import AchatMPSL, MouvementStock, Stock
from produits.models import Produit


def _d(val) -> Decimal:
    """Convertit None ou toute valeur en Decimal."""
    return Decimal(str(val)) if val is not None else Decimal("0")


class Command(BaseCommand):
    help = "Synchronise le stock MPSL depuis les achats et transferts (resync données historiques)."

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
                "=== DRY-RUN (aucune modification) "
                "— relancer avec --commit pour appliquer ==="
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
        total_ignores = 0

        for lieu in lieux_qs:
            self.stdout.write(f"\n── Lieu : {lieu.nom} (#{lieu.pk}, {lieu.entreprise})")
            self.stdout.write(
                f"   {'Produit':<30} {'Initial':>12} {'Transféré':>12} "
                f"{'Restant':>12} {'Actuel':>12}  Statut"
            )
            self.stdout.write("   " + "─" * 90)

            # ── 2. Périmètre : union des produits avec achats + produits déjà en stock ──
            noms_achats = set(
                AchatMPSL.objects
                .filter(lieu=lieu)
                .values_list("produit_nom", flat=True)
                .distinct()
            )
            noms_stock = set(
                Stock.objects
                .filter(lieu=lieu)
                .select_related("produit")
                .values_list("produit__nom", flat=True)
            )
            tous_noms = noms_achats | noms_stock

            if not tous_noms:
                self.stdout.write("   Aucun produit trouvé (ni achats ni stock).")
                continue

            for nom in sorted(tous_noms, key=str.lower):

                # ── 3. Résoudre le Produit FK ──────────────────────────────────
                produit = Produit.objects.filter(
                    nom__iexact=nom,
                    entreprise_id=lieu.entreprise_id,
                ).first()

                if produit is None:
                    self.stdout.write(self.style.WARNING(
                        f"   ⚠  '{nom}' introuvable dans le catalogue — ignoré."
                    ))
                    total_ignores += 1
                    continue

                produit_unite = (produit.unite or "kg").strip().lower()

                # ── 4. Total entrant : achats ──────────────────────────────────
                achats_qs = AchatMPSL.objects.filter(lieu=lieu, produit_nom__iexact=nom)

                total_sac_in = _d(
                    achats_qs.filter(unite__in=("sac", "sacs"))
                    .aggregate(s=Sum("quantite"))["s"]
                )
                total_kg_in = _d(
                    achats_qs.filter(unite="kg")
                    .aggregate(s=Sum("quantite"))["s"]
                )
                total_tonne_in = _d(
                    achats_qs.filter(unite__in=("tonne", "tonnes"))
                    .aggregate(s=Sum("quantite"))["s"]
                )
                total_kg_in += total_tonne_in * Decimal("1000")

                # ── 5. Total sortant : transferts depuis ce lieu MPSL ──────────
                # MouvementStock n'a pas de champ unité : approximation par unite native.
                total_mvt = _d(
                    MouvementStock.objects
                    .filter(produit=produit, transfert__from_lieu=lieu)
                    .aggregate(s=Sum("quantite"))["s"]
                )

                if produit_unite in ("sac", "sacs"):
                    sac_out = total_mvt
                    kg_out  = Decimal("0")
                else:
                    sac_out = Decimal("0")
                    kg_out  = total_mvt

                # ── 6. État actuel du stock ────────────────────────────────────
                stock = Stock.objects.filter(produit=produit, lieu=lieu).first()
                current_sac = _d(stock.quantite)    if stock else Decimal("0")
                current_kg  = _d(stock.quantite_kg) if stock else Decimal("0")

                # ── 7. Stock net attendu ───────────────────────────────────────
                expected_sac = max(Decimal("0"), total_sac_in - sac_out)

                # Produit sac : quantite_kg vient des conversions → préservée.
                # Produit kg  : quantite_kg vient des achats → recalculée.
                if produit_unite in ("sac", "sacs"):
                    expected_kg = current_kg
                else:
                    expected_kg = max(Decimal("0"), total_kg_in - kg_out)

                # ── 8. Ligne de rapport ────────────────────────────────────────
                # Résumé sur une ligne : initial / transféré / restant / actuel
                if produit_unite in ("sac", "sacs"):
                    initial_str    = f"{total_sac_in:.0f} sacs"
                    transfere_str  = f"{sac_out:.0f} sacs"
                    restant_str    = f"{expected_sac:.0f} sacs"
                    actuel_str     = f"{current_sac:.0f} sacs"
                    if current_kg > 0:
                        actuel_str += f" +{current_kg:.0f}kg"
                else:
                    initial_str    = f"{total_kg_in:.2f} kg"
                    transfere_str  = f"{kg_out:.2f} kg"
                    restant_str    = f"{expected_kg:.2f} kg"
                    actuel_str     = f"{current_kg:.2f} kg"

                unchanged = (current_sac == expected_sac and current_kg == expected_kg)

                if unchanged:
                    statut = "✓ OK"
                    total_inchanges += 1
                elif not stock:
                    statut = "→ À CRÉER"
                    total_crees += 1
                else:
                    statut = "→ À CORRIGER"
                    total_maj += 1

                nom_tronc = (produit.nom[:28] + "..") if len(produit.nom) > 30 else produit.nom
                ligne = (
                    f"   {nom_tronc:<30} {initial_str:>12} {transfere_str:>12} "
                    f"{restant_str:>12} {actuel_str:>12}  {statut}"
                )

                if unchanged:
                    self.stdout.write(ligne)
                else:
                    self.stdout.write(self.style.SUCCESS(ligne) if commit else ligne)

                # ── 9. Appliquer si --commit ───────────────────────────────────
                if commit and not unchanged:
                    with transaction.atomic():
                        if stock is None:
                            Stock.objects.create(
                                produit=produit,
                                lieu=lieu,
                                quantite=expected_sac,
                                quantite_kg=expected_kg,
                            )
                        else:
                            stock = Stock.objects.select_for_update().get(pk=stock.pk)
                            stock.quantite    = expected_sac
                            stock.quantite_kg = expected_kg
                            stock.save(update_fields=["quantite", "quantite_kg", "updated_at"])

            self.stdout.write("   " + "─" * 90)

        # ── Synthèse ──────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write("=" * 60)

        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Terminé : {total_crees} créés, {total_maj} corrigés, "
                f"{total_inchanges} inchangés, {total_ignores} ignorés."
            ))
        else:
            msg = (
                f"DRY-RUN : {total_crees} à créer, {total_maj} à corriger, "
                f"{total_inchanges} conformes, {total_ignores} ignorés."
            )
            if total_crees + total_maj > 0:
                msg += " — Relancer avec --commit pour appliquer."
                self.stdout.write(self.style.WARNING(msg))
            else:
                self.stdout.write(self.style.SUCCESS(f"✓ CONFORME — {msg}"))
