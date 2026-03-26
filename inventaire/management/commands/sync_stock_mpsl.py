"""
Commande à deux modes :

MODE 1 — Synchronisation du stock (défaut)
    Recalcule et corrige les enregistrements Stock MPSL à partir des AchatMPSL
    et des MouvementStock existants. Utile pour les achats antérieurs à l'activation
    de la mise à jour stock automatique.

MODE 2 — Transfert vers boutique ou usine (--transferer)
    Calcule le stock restant RÉEL depuis la source primaire :
        restant = Σ(AchatMPSL) − Σ(MouvementStock déjà transférés)
    Affiche la liste avec comparaison vs table Stock (⚠ si désynchronisé).
    En --commit :
      1. Synchronise la table Stock (comme Mode 1) pour garantir la cohérence.
      2. Crée le Transfert + MouvementStock via transfert_depuis_mpsl() (atomique).
    Aucune donnée existante n'est supprimée ni modifiée.

    Destinations autorisées : boutique (magasin) OU usine.

Usage :
    python manage.py sync_stock_mpsl                                # Mode 1 dry-run
    python manage.py sync_stock_mpsl --commit                       # Mode 1 appliquer
    python manage.py sync_stock_mpsl --lieu=<pk>                    # Restreindre lieu MPSL

    python manage.py sync_stock_mpsl --transferer                           # Mode 2 dry-run
    python manage.py sync_stock_mpsl --transferer --destination=<pk>        # Mode 2 dry-run ciblé
    python manage.py sync_stock_mpsl --transferer --destination=<pk> --commit  # Mode 2 appliquer
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import Lieu
from inventaire.models import AchatMPSL, MouvementStock, Stock
from inventaire.services import ErreurStock, transfert_depuis_mpsl
from produits.models import Produit


def _d(val) -> Decimal:
    """Convertit None ou toute valeur en Decimal."""
    return Decimal(str(val)) if val is not None else Decimal("0")


def _calculer_restant(produit, lieu):
    """
    Calcule le stock restant RÉEL depuis la source primaire.

    restant_sac = Σ(AchatMPSL en sacs) − Σ(MouvementStock depuis MPSL)
    restant_kg  = Σ(AchatMPSL en kg/tonnes) − Σ(MouvementStock depuis MPSL)

    Retourne (total_sac_in, total_kg_in, deja_transfere, restant_sac, restant_kg,
              produit_unite).
    """
    produit_unite = (produit.unite or "kg").strip().lower()
    achats_qs = AchatMPSL.objects.filter(lieu=lieu, produit_nom__iexact=produit.nom)

    total_sac_in = _d(
        achats_qs.filter(unite__in=("sac", "sacs"))
        .aggregate(s=Sum("quantite"))["s"]
    )
    total_kg_in = _d(
        achats_qs.filter(unite="kg")
        .aggregate(s=Sum("quantite"))["s"]
    )
    total_kg_in += _d(
        achats_qs.filter(unite__in=("tonne", "tonnes"))
        .aggregate(s=Sum("quantite"))["s"]
    ) * Decimal("1000")

    # Tous les mouvements sortants depuis ce MPSL vers boutiques ou usines
    deja_transfere = _d(
        MouvementStock.objects
        .filter(
            produit=produit,
            transfert__from_lieu=lieu,
            transfert__to_lieu__type_lieu__in=(Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE),
        )
        .aggregate(s=Sum("quantite"))["s"]
    )

    if produit_unite in ("sac", "sacs"):
        restant_sac = max(Decimal("0"), total_sac_in - deja_transfere)
        restant_kg  = Decimal("0")  # quantite_kg (conversions) préservée séparément
    else:
        restant_sac = Decimal("0")
        restant_kg  = max(Decimal("0"), total_kg_in - deja_transfere)

    return total_sac_in, total_kg_in, deja_transfere, restant_sac, restant_kg, produit_unite


class Command(BaseCommand):
    help = (
        "Mode 1 : synchronise le stock MPSL depuis les achats/transferts. "
        "Mode 2 (--transferer) : calcule le stock restant depuis la source primaire "
        "et crée les transferts vers boutique ou usine."
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
            help="Mode 2 : transfère le stock restant vers boutique ou usine.",
        )
        parser.add_argument(
            "--destination",
            type=int,
            default=None,
            help="Boutique ou usine de destination (pk) — requis si plusieurs lieux disponibles.",
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
                f"   {'Produit':<30} {'Total acheté':>14} {'Transféré':>12} "
                f"{'Restant réel':>14} {'Table actuelle':>15}  Statut"
            )
            self.stdout.write("   " + "─" * 100)

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

                total_sac_in, total_kg_in, deja_transfere, expected_sac, expected_kg, produit_unite = \
                    _calculer_restant(produit, lieu)

                stock = Stock.objects.filter(produit=produit, lieu=lieu).first()
                current_sac = _d(stock.quantite)    if stock else Decimal("0")
                current_kg  = _d(stock.quantite_kg) if stock else Decimal("0")

                # Pour les produits en sacs : préserver quantite_kg (conversions)
                if produit_unite in ("sac", "sacs"):
                    expected_kg = current_kg

                if produit_unite in ("sac", "sacs"):
                    initial_str   = f"{total_sac_in:.0f} sacs"
                    transfere_str = f"{deja_transfere:.0f} sacs"
                    restant_str   = f"{expected_sac:.0f} sacs"
                    actuel_str    = f"{current_sac:.0f} sacs"
                    if current_kg > 0:
                        actuel_str += f" +{current_kg:.0f}kg"
                else:
                    initial_str   = f"{total_kg_in:.2f} kg"
                    transfere_str = f"{deja_transfere:.2f} kg"
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
                    f"   {nom_tronc:<30} {initial_str:>14} {transfere_str:>12} "
                    f"{restant_str:>14} {actuel_str:>15}  {statut}"
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

            self.stdout.write("   " + "─" * 100)

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
    # MODE 2 — Transfert vers boutique ou usine
    # ══════════════════════════════════════════════════════════════════════════

    def _run_transferer(self, lieux_qs, destination_pk, commit):
        """
        Calcule le stock restant depuis la source primaire (AchatMPSL − MouvementStock),
        affiche la liste complète (dry-run ou pas), puis en --commit :
          1. Synchronise la table Stock avec les valeurs recalculées.
          2. Crée le transfert via transfert_depuis_mpsl() (atomique, auditable).

        Garanties :
          - Aucun transfert existant n'est modifié ni supprimé.
          - Le calcul du restant est toujours basé sur la source de vérité (achats − historique).
          - La table Stock est mise à jour avant le transfert pour éviter tout rejet.
        """
        total_transferes = 0
        total_ignores = 0
        total_vides = 0

        for lieu in lieux_qs:
            boutique = self._resoudre_destination(lieu, destination_pk)
            if boutique is None:
                continue

            type_dest = "boutique" if boutique.type_lieu == Lieu.TYPE_MAGASIN else "usine"
            self.stdout.write(
                f"\n── Lieu MPSL : {lieu.nom} (#{lieu.pk}) → {boutique.nom} (#{boutique.pk}, {type_dest})"
            )
            self.stdout.write(
                f"   {'Produit':<30} {'Total acheté':>14} {'Déjà transféré':>16} "
                f"{'Restant réel':>14} {'Table Stock':>12}  Statut"
            )
            self.stdout.write("   " + "─" * 105)

            # Périmètre : tous les produits ayant des achats MPSL pour ce lieu
            noms_achats = list(
                AchatMPSL.objects
                .filter(lieu=lieu)
                .values_list("produit_nom", flat=True)
                .distinct()
            )

            if not noms_achats:
                self.stdout.write("   Aucun achat MPSL enregistré pour ce dépôt.")
                self.stdout.write("   " + "─" * 105)
                continue

            lignes_a_transferer = []  # [(produit, a_transferer, unite, restant_sac, restant_kg)]

            for nom in sorted(noms_achats, key=str.lower):
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

                total_sac_in, total_kg_in, deja_transfere, restant_sac, restant_kg, produit_unite = \
                    _calculer_restant(produit, lieu)

                # Valeur actuelle dans la table Stock
                stock_obj = Stock.objects.filter(produit=produit, lieu=lieu).first()
                table_sac = _d(stock_obj.quantite)    if stock_obj else Decimal("0")
                table_kg  = _d(stock_obj.quantite_kg) if stock_obj else Decimal("0")

                # Pour les sacs : quantite_kg (conversions) est préservée, ne compte pas ici
                if produit_unite in ("sac", "sacs"):
                    total_str   = f"{total_sac_in:.0f} sacs"
                    deja_str    = f"{deja_transfere:.0f} sacs"
                    restant_str = f"{restant_sac:.0f} sacs"
                    table_str   = f"{table_sac:.0f} sacs"
                    a_transferer   = restant_sac
                    unite_transfer = "sacs"
                    desync = (table_sac != restant_sac)
                else:
                    total_str   = f"{total_kg_in:.2f} kg"
                    deja_str    = f"{deja_transfere:.2f} kg"
                    restant_str = f"{restant_kg:.2f} kg"
                    table_str   = f"{table_kg:.2f} kg"
                    a_transferer   = restant_kg
                    unite_transfer = "kg"
                    desync = (table_kg != restant_kg)

                desync_flag = " ⚠DÉSYNC" if desync else ""
                nom_tronc = (produit.nom[:28] + "..") if len(produit.nom) > 30 else produit.nom

                if a_transferer <= 0:
                    statut = "— épuisé"
                    total_vides += 1
                    self.stdout.write(
                        f"   {nom_tronc:<30} {total_str:>14} {deja_str:>16} "
                        f"{restant_str:>14} {table_str:>12}  {statut}{desync_flag}"
                    )
                    continue

                statut = "→ À TRANSFÉRER"
                total_transferes += 1
                ligne = (
                    f"   {nom_tronc:<30} {total_str:>14} {deja_str:>16} "
                    f"{restant_str:>14} {table_str:>12}  {statut}{desync_flag}"
                )
                self.stdout.write(self.style.SUCCESS(ligne) if commit else ligne)
                lignes_a_transferer.append(
                    (produit, a_transferer, unite_transfer, restant_sac, restant_kg, table_kg)
                )

            self.stdout.write("   " + "─" * 105)

            if not lignes_a_transferer:
                self.stdout.write("   Aucune quantité à transférer.")
                continue

            if not commit:
                continue

            # ── COMMIT : Étape 1 — Synchroniser la table Stock ────────────────
            # Garantit que transfert_depuis_mpsl() trouve les bonnes quantités.
            # Les quantite_kg (conversions en cours) des produits en sacs sont préservées.
            self.stdout.write("   Étape 1/2 — Synchronisation table Stock...")
            try:
                with transaction.atomic():
                    for produit, _, unite_transfer, restant_sac, restant_kg, table_kg_original in lignes_a_transferer:
                        produit_unite = (produit.unite or "kg").strip().lower()
                        stock_obj = Stock.objects.filter(produit=produit, lieu=lieu).first()

                        if stock_obj is None:
                            # Produit en sacs : quantite_kg = 0 (pas de conversion existante)
                            Stock.objects.create(
                                produit=produit,
                                lieu=lieu,
                                quantite=restant_sac,
                                quantite_kg=restant_kg,
                            )
                        else:
                            s = Stock.objects.select_for_update().get(pk=stock_obj.pk)
                            s.quantite = restant_sac
                            if produit_unite not in ("sac", "sacs"):
                                # Produit kg : mettre à jour quantite_kg aussi
                                s.quantite_kg = restant_kg
                            # Pour les sacs : quantite_kg (conversions) reste inchangée
                            s.save(update_fields=["quantite", "quantite_kg", "updated_at"])
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"   ✗ Synchronisation échouée : {exc}"))
                total_ignores += len(lignes_a_transferer)
                total_transferes -= len(lignes_a_transferer)
                continue

            # ── COMMIT : Étape 2 — Créer le transfert ─────────────────────────
            self.stdout.write("   Étape 2/2 — Création du transfert...")
            lignes_service = [
                (produit, a_transferer, unite_transfer)
                for produit, a_transferer, unite_transfer, _, __, ___ in lignes_a_transferer
            ]
            try:
                transfert = transfert_depuis_mpsl(
                    from_mpsl=lieu,
                    to_lieu=boutique,
                    lignes=lignes_service,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"   ✓ Transfert #{transfert.pk} créé ({len(lignes_service)} produit(s))."
                ))
            except ErreurStock as e:
                self.stdout.write(self.style.ERROR(f"   ✗ Erreur transfert : {e}"))
                total_ignores += len(lignes_service)
                total_transferes -= len(lignes_service)

        self.stdout.write("")
        self.stdout.write("=" * 60)
        if commit:
            if total_transferes > 0:
                self.stdout.write(self.style.SUCCESS(
                    f"Terminé : {total_transferes} produit(s) transféré(s), "
                    f"{total_vides} épuisé(s), {total_ignores} erreur(s)."
                ))
            else:
                msg = f"Aucun transfert effectué. {total_vides} produit(s) épuisé(s)."
                if total_ignores:
                    msg += f" {total_ignores} erreur(s)."
                self.stdout.write(self.style.WARNING(msg))
        else:
            if total_transferes > 0:
                self.stdout.write(self.style.WARNING(
                    f"DRY-RUN : {total_transferes} produit(s) à transférer, "
                    f"{total_vides} épuisé(s). — Relancer avec --commit pour appliquer."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Aucun stock à transférer ({total_vides} produit(s) épuisé(s))."
                ))

    def _resoudre_destination(self, lieu_mpsl, destination_pk):
        """
        Résout la destination (boutique OU usine) pour un lieu MPSL donné.
        - Si --destination=<pk> fourni : vérifie appartenance et type.
        - Sinon : auto-sélection si un seul lieu destination dans l'entreprise.
        - Si plusieurs destinations et pas de --destination : liste et erreur explicite.
        """
        ent_id = lieu_mpsl.entreprise_id
        destinations_qs = Lieu.objects.filter(
            type_lieu__in=(Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE),
            entreprise_id=ent_id,
        )

        if destination_pk:
            dest = destinations_qs.filter(pk=destination_pk).first()
            if dest is None:
                self.stdout.write(self.style.ERROR(
                    f"   ✗ Lieu #{destination_pk} introuvable, hors entreprise "
                    f"'{lieu_mpsl.entreprise}', ou n'est pas une boutique/usine."
                ))
                return None
            return dest

        count = destinations_qs.count()
        if count == 1:
            return destinations_qs.first()
        if count == 0:
            self.stdout.write(self.style.ERROR(
                f"   ✗ Aucune boutique ni usine dans l'entreprise '{lieu_mpsl.entreprise}'."
            ))
            return None

        # Plusieurs destinations disponibles → afficher la liste
        self.stdout.write(self.style.ERROR(
            f"   ✗ {count} destinations disponibles dans '{lieu_mpsl.entreprise}'. "
            f"Précise --destination=<pk> :"
        ))
        for d in destinations_qs.order_by("type_lieu", "nom"):
            label = "boutique" if d.type_lieu == Lieu.TYPE_MAGASIN else "usine"
            self.stdout.write(f"       #{d.pk}  {d.nom}  ({label})")
        return None
