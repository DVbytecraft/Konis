"""
Commande à deux modes :

MODE 1 — Synchronisation du stock (défaut)
    Recalcule et corrige les enregistrements Stock MPSL à partir des AchatMPSL
    et des MouvementStock existants. Utile pour les achats antérieurs à l'activation
    de la mise à jour stock automatique.

MODE 2 — Transfert vers boutique (--transferer)
    Pour chaque produit ayant du stock restant au dépôt MPSL, crée un Transfert
    + MouvementStock vers la boutique indiquée par --destination. Réutilise le
    service transfert_depuis_mpsl() : atomique, contrôlé, auditable.

    Règle : on ne touche qu'aux quantités disponibles en stock MPSL.
            Les transferts existants (vers boutiques ou usines) ne sont jamais modifiés.

Usage :
    python manage.py sync_stock_mpsl                               # Mode 1 dry-run
    python manage.py sync_stock_mpsl --commit                      # Mode 1 appliquer
    python manage.py sync_stock_mpsl --lieu=<pk>                   # Restreindre lieu MPSL

    python manage.py sync_stock_mpsl --transferer --destination=<pk>           # Mode 2 dry-run
    python manage.py sync_stock_mpsl --transferer --destination=<pk> --commit  # Mode 2 appliquer
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum

from core.models import Lieu
from inventaire.models import AchatMPSL, MouvementStock, Stock, Transfert
from inventaire.services import ErreurStock, transfert_depuis_mpsl
from produits.models import Produit


def _d(val) -> Decimal:
    """Convertit None ou toute valeur en Decimal."""
    return Decimal(str(val)) if val is not None else Decimal("0")


class Command(BaseCommand):
    help = (
        "Mode 1 : synchronise le stock MPSL depuis les achats/transferts. "
        "Mode 2 (--transferer) : crée les transferts vers boutique pour le stock restant."
    )

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
            help="Restreint à un seul lieu MPSL (pk).",
        )
        parser.add_argument(
            "--transferer",
            action="store_true",
            default=False,
            help="Mode 2 : crée les transferts vers boutique pour le stock restant.",
        )
        parser.add_argument(
            "--destination",
            type=int,
            default=None,
            help="Boutique de destination (pk) — requis en mode --transferer si plusieurs boutiques.",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        lieu_filter = options["lieu"]
        mode_transferer = options["transferer"]
        destination_pk = options["destination"]

        if not commit:
            self.stdout.write(self.style.WARNING(
                "=== DRY-RUN (aucune modification) "
                "— relancer avec --commit pour appliquer ==="
            ))

        # ── Sélectionner les lieux MPSL concernés ─────────────────────────────
        lieux_qs = Lieu.objects.filter(type_lieu=Lieu.TYPE_MPSL).select_related("entreprise")
        if lieu_filter:
            lieux_qs = lieux_qs.filter(pk=lieu_filter)

        if not lieux_qs.exists():
            self.stdout.write(self.style.ERROR("Aucun lieu MPSL trouvé."))
            return

        if mode_transferer:
            self._run_transferer(lieux_qs, destination_pk, commit)
        else:
            self._run_sync(lieux_qs, commit)

    # ══════════════════════════════════════════════════════════════════════════
    # MODE 1 — Synchronisation du stock
    # ══════════════════════════════════════════════════════════════════════════

    def _run_sync(self, lieux_qs, commit):
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

            # Périmètre : union achats + stock existants
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

                # Total entrant : achats
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

                # Total sortant : tous les transferts depuis ce lieu MPSL
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

                # État actuel du stock
                stock = Stock.objects.filter(produit=produit, lieu=lieu).first()
                current_sac = _d(stock.quantite)    if stock else Decimal("0")
                current_kg  = _d(stock.quantite_kg) if stock else Decimal("0")

                # Stock net attendu
                expected_sac = max(Decimal("0"), total_sac_in - sac_out)
                if produit_unite in ("sac", "sacs"):
                    expected_kg = current_kg  # conversions → préservées
                else:
                    expected_kg = max(Decimal("0"), total_kg_in - kg_out)

                # Rapport
                if produit_unite in ("sac", "sacs"):
                    initial_str   = f"{total_sac_in:.0f} sacs"
                    transfere_str = f"{sac_out:.0f} sacs"
                    restant_str   = f"{expected_sac:.0f} sacs"
                    actuel_str    = f"{current_sac:.0f} sacs"
                    if current_kg > 0:
                        actuel_str += f" +{current_kg:.0f}kg"
                else:
                    initial_str   = f"{total_kg_in:.2f} kg"
                    transfere_str = f"{kg_out:.2f} kg"
                    restant_str   = f"{expected_kg:.2f} kg"
                    actuel_str    = f"{current_kg:.2f} kg"

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

    # ══════════════════════════════════════════════════════════════════════════
    # MODE 2 — Transfert vers boutique
    # ══════════════════════════════════════════════════════════════════════════

    def _run_transferer(self, lieux_qs, destination_pk, commit):
        total_transferes = 0
        total_ignores = 0
        total_vides = 0

        for lieu in lieux_qs:
            # ── Résoudre la boutique de destination ───────────────────────────
            boutique = self._resoudre_destination(lieu, destination_pk)
            if boutique is None:
                continue

            self.stdout.write(
                f"\n── Lieu MPSL : {lieu.nom} (#{lieu.pk}) → {boutique.nom} (#{boutique.pk})"
            )
            self.stdout.write(
                f"   {'Produit':<30} {'Stock MPSL':>12} {'Déjà boutiques':>16} "
                f"{'À transférer':>14}  Statut"
            )
            self.stdout.write("   " + "─" * 95)

            stocks_mpsl = (
                Stock.objects
                .filter(lieu=lieu)
                .select_related("produit")
                .order_by("produit__nom")
            )

            if not stocks_mpsl.exists():
                self.stdout.write("   Aucun stock en dépôt MPSL.")
                continue

            lignes_a_transferer = []

            for stock in stocks_mpsl:
                produit = stock.produit
                produit_unite = (produit.unite or "kg").strip().lower()

                # Quantité actuelle au MPSL
                qte_sac = _d(stock.quantite)
                qte_kg  = _d(stock.quantite_kg)

                # Total historique déjà envoyé vers les boutiques (magasins)
                deja_boutiques = _d(
                    MouvementStock.objects
                    .filter(
                        produit=produit,
                        transfert__from_lieu=lieu,
                        transfert__to_lieu__type_lieu=Lieu.TYPE_MAGASIN,
                    )
                    .aggregate(s=Sum("quantite"))["s"]
                )

                # Quantité et unité à transférer
                if produit_unite in ("sac", "sacs"):
                    a_transferer = qte_sac
                    unite_transfer = "sacs"
                    stock_str    = f"{qte_sac:.0f} sacs"
                    deja_str     = f"{deja_boutiques:.0f} sacs"
                    transfer_str = f"{a_transferer:.0f} sacs"
                else:
                    a_transferer = qte_kg
                    unite_transfer = "kg"
                    stock_str    = f"{qte_kg:.2f} kg"
                    deja_str     = f"{deja_boutiques:.2f} kg"
                    transfer_str = f"{a_transferer:.2f} kg"

                nom_tronc = (produit.nom[:28] + "..") if len(produit.nom) > 30 else produit.nom

                if a_transferer <= 0:
                    statut = "— stock vide"
                    total_vides += 1
                    self.stdout.write(
                        f"   {nom_tronc:<30} {stock_str:>12} {deja_str:>16} "
                        f"{transfer_str:>14}  {statut}"
                    )
                    continue

                statut = "→ À TRANSFÉRER"
                total_transferes += 1
                ligne = (
                    f"   {nom_tronc:<30} {stock_str:>12} {deja_str:>16} "
                    f"{transfer_str:>14}  {statut}"
                )
                self.stdout.write(self.style.SUCCESS(ligne) if commit else ligne)

                lignes_a_transferer.append((produit, a_transferer, unite_transfer))

            self.stdout.write("   " + "─" * 95)

            if not lignes_a_transferer:
                self.stdout.write("   Aucune quantité à transférer.")
                continue

            # ── Appliquer si --commit ──────────────────────────────────────────
            if commit:
                try:
                    transfert = transfert_depuis_mpsl(
                        from_mpsl=lieu,
                        to_lieu=boutique,
                        lignes=lignes_a_transferer,
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f"   ✓ Transfert #{transfert.pk} créé ({len(lignes_a_transferer)} produit(s))."
                    ))
                except ErreurStock as e:
                    self.stdout.write(self.style.ERROR(f"   ✗ Erreur : {e}"))
                    total_ignores += 1
                    total_transferes -= len(lignes_a_transferer)

        self.stdout.write("")
        self.stdout.write("=" * 60)
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Terminé : {total_transferes} produit(s) transféré(s), "
                f"{total_vides} stock(s) vide(s), {total_ignores} erreur(s)."
            ))
        else:
            if total_transferes > 0:
                self.stdout.write(self.style.WARNING(
                    f"DRY-RUN : {total_transferes} produit(s) à transférer, "
                    f"{total_vides} stock(s) vide(s). — Relancer avec --commit pour appliquer."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Aucun stock à transférer ({total_vides} produit(s) avec stock vide)."
                ))

    def _resoudre_destination(self, lieu_mpsl, destination_pk):
        """
        Résout la boutique de destination pour un lieu MPSL donné.
        - Si --destination=<pk> fourni : vérifie que c'est un magasin de la même entreprise.
        - Sinon : auto-sélection si une seule boutique dans l'entreprise.
        - Si plusieurs boutiques et pas de --destination : erreur explicite.
        """
        ent_id = lieu_mpsl.entreprise_id
        boutiques_qs = Lieu.objects.filter(type_lieu=Lieu.TYPE_MAGASIN, entreprise_id=ent_id)

        if destination_pk:
            boutique = boutiques_qs.filter(pk=destination_pk).first()
            if boutique is None:
                self.stdout.write(self.style.ERROR(
                    f"   ✗ Boutique #{destination_pk} introuvable ou hors entreprise '{lieu_mpsl.entreprise}'."
                ))
                return None
            return boutique

        count = boutiques_qs.count()
        if count == 1:
            return boutiques_qs.first()
        if count == 0:
            self.stdout.write(self.style.ERROR(
                f"   ✗ Aucune boutique dans l'entreprise '{lieu_mpsl.entreprise}'."
            ))
            return None

        # Plusieurs boutiques → afficher la liste et demander --destination
        self.stdout.write(self.style.ERROR(
            f"   ✗ {count} boutiques disponibles dans '{lieu_mpsl.entreprise}'. "
            f"Précise --destination=<pk> :"
        ))
        for b in boutiques_qs.order_by("nom"):
            self.stdout.write(f"       #{b.pk}  {b.nom}")
        return None
