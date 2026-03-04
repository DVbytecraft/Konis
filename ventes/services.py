"""
Services ventes KONIS : vente boutique, numéro de ticket automatique.
Transaction atomique. Historique via Ticket + LigneVente.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Produit
from ventes.models import LigneVente, Ticket

UNIT_KG = "kg"
UNIT_TONNE = "tonne"
UNIT_SAC = "sac"


def _normalize_mouture_unit(raw_unit: str) -> str | None:
    """Map product unit text to a mouture billing unit."""
    unit = (raw_unit or "").strip().lower()
    if "kg" in unit:
        return UNIT_KG
    if "tonne" in unit:
        return UNIT_TONNE
    if "sac" in unit:
        return UNIT_SAC
    return None


def _compute_boutique_totals(
    lignes: list[tuple[Produit, Decimal, Decimal]],
    *,
    mouture: bool,
    prix_mouture_kg: Decimal | None,
    prix_mouture_tonne: Decimal | None,
    prix_mouture_sac: Decimal | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Single source of truth for boutique sale totals.

    Returns (montant_produits, cout_mouture, montant_total).
    """
    montant_produits = sum((quantite * prix_unitaire for _, quantite, prix_unitaire in lignes), Decimal("0"))

    if not mouture:
        return montant_produits, Decimal("0"), montant_produits

    prix_by_unit: dict[str, Decimal | None] = {
        UNIT_KG: prix_mouture_kg,
        UNIT_TONNE: prix_mouture_tonne,
        UNIT_SAC: prix_mouture_sac,
    }
    cout_mouture = Decimal("0")

    for produit, quantite, _ in lignes:
        unit_key = _normalize_mouture_unit(produit.unite or "")
        if unit_key is None:
            raise ErreurStock(
                f"Mouture demandee: unite produit non supportee pour {produit.nom} ({produit.unite})."
            )
        unit_price = prix_by_unit[unit_key]
        if unit_price is None:
            raise ErreurStock(
                f"Mouture demandee: prix mouture manquant pour l'unite '{unit_key}' (produit {produit.nom})."
            )
        cout_mouture += quantite * unit_price

    return montant_produits, cout_mouture, montant_produits + cout_mouture


def generer_numero_ticket(lieu: Lieu) -> str:
    """
    Génère le prochain numéro de ticket pour un lieu (séquence par jour).
    Format : KONIS-{CODE_LIEU}-{YYYYMMDD}-{SEQ:06d}
    Exemple : KONIS-CENTRE-20260208-000123
    Unicité garantie par verrouillage du lieu (select_for_update) dans la transaction.
    """
    today = timezone.now().date()
    # Verrouiller le lieu pour sérialiser la génération du numéro (évite doublons concurrents)
    Lieu.objects.select_for_update().get(pk=lieu.pk)
    count = Ticket.objects.filter(lieu=lieu, date__date=today).count()
    seq = count + 1
    code = (lieu.code or "").strip().upper() or f"L{lieu.id}"
    # Code alphanumérique uniquement (sécurité)
    code = "".join(c for c in code if c.isalnum())[:10] or f"L{lieu.id}"
    return f"KONIS-{code}-{today:%Y%m%d}-{seq:06d}"


def vente_boutique(
    lieu: Lieu,
    lignes: list[tuple[Produit, Decimal, Decimal]],
    *,
    mouture: bool = False,
    prix_mouture_kg: Decimal | None = None,
    prix_mouture_tonne: Decimal | None = None,
    prix_mouture_sac: Decimal | None = None,
) -> Ticket:
    """
    Enregistre une vente en boutique (ticket + lignes + mouture optionnelle).
    Transaction atomique. Numéro de ticket généré automatiquement.
    Lève ErreurStock si stock insuffisant.

    lignes : liste de (produit, quantite, prix_unitaire)
    mouture : True si le client demande l'écrasement (mouture)
    prix_mouture_kg/tonne/sac : prix par unité selon l'unité du produit.
      Coût mouture par ligne = quantite × prix_mouture_{unite_du_produit}
    """
    if lieu.type_lieu != Lieu.TYPE_MAGASIN:
        raise ErreurStock(f"Le lieu {lieu} n'est pas un magasin.")

    with transaction.atomic():
        # Verrouiller et vérifier les stocks
        for produit, quantite, _ in lignes:
            if quantite <= 0:
                raise ErreurStock(f"Quantité invalide pour {produit}: {quantite}")
            try:
                stock = Stock.objects.select_for_update().get(
                    produit=produit, lieu=lieu
                )
            except Stock.DoesNotExist:
                raise ErreurStock(f"Pas de stock pour {produit} à {lieu}.")
            if stock.quantite < quantite:
                raise ErreurStock(
                    f"Stock insuffisant pour {produit} à {lieu}: "
                    f"disponible {stock.quantite}, demandé {quantite}."
                )

        montant_produits, cout_mouture, montant_total = _compute_boutique_totals(
            lignes,
            mouture=mouture,
            prix_mouture_kg=prix_mouture_kg,
            prix_mouture_tonne=prix_mouture_tonne,
            prix_mouture_sac=prix_mouture_sac,
        )

        ticket = None
        for _ in range(5):
            numero = generer_numero_ticket(lieu)
            try:
                ticket = Ticket.objects.create(
                    lieu=lieu,
                    numero=numero,
                    mouture=mouture,
                    prix_mouture_kg=prix_mouture_kg if mouture else None,
                    prix_mouture_tonne=prix_mouture_tonne if mouture else None,
                    prix_mouture_sac=prix_mouture_sac if mouture else None,
                    cout_mouture=cout_mouture,
                    montant_total=montant_total,
                )
                break
            except IntegrityError:
                # Concurrence rare sur le numero : relancer la generation.
                continue
        if ticket is None:
            raise ErreurStock("Impossible de generer un numero de ticket unique.")

        for produit, quantite, prix_unitaire in lignes:
            LigneVente.objects.create(
                ticket=ticket,
                produit=produit,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
            )

            stock = Stock.objects.select_for_update().get(
                produit=produit, lieu=lieu
            )
            stock.quantite -= quantite
            stock.save(update_fields=["quantite"])

    return ticket


def vente_mouture_seule(
    lieu: Lieu,
    quantite: Decimal,
    unite: str,
    prix_unitaire: Decimal,
    produit_apporte: str = "",
    idempotency_key: str | None = None,
) -> tuple[Ticket, bool]:
    """
    Ticket mouture-seule : aucun produit, aucune déduction de stock.
    Pour les clients qui viennent uniquement faire moudre leur grain.
    Fonctionne pour boutiques ET usines.
    Retourne (ticket, created) où created=False indique un replay idempotent.
    """
    key = (idempotency_key or "").strip() or None

    with transaction.atomic():
        if key:
            existing = (
                Ticket.objects.select_for_update()
                .filter(lieu=lieu, idempotency_key=key, mouture=True)
                .first()
            )
            if existing is not None:
                return existing, False

        cout = quantite * prix_unitaire
        ticket = None
        for _ in range(5):
            numero = generer_numero_ticket(lieu)
            try:
                ticket = Ticket.objects.create(
                    lieu=lieu,
                    numero=numero,
                    idempotency_key=key,
                    produit_apporte=produit_apporte,
                    mouture=True,
                    prix_mouture_kg=prix_unitaire if "kg" in unite.lower() else None,
                    prix_mouture_tonne=prix_unitaire if "tonne" in unite.lower() else None,
                    prix_mouture_sac=prix_unitaire if "sac" in unite.lower() else None,
                    cout_mouture=cout,
                    montant_total=cout,
                )
                return ticket, True
            except IntegrityError:
                if key:
                    existing = Ticket.objects.filter(
                        lieu=lieu,
                        idempotency_key=key,
                        mouture=True,
                    ).first()
                    if existing is not None:
                        return existing, False
                continue

    raise ErreurStock("Impossible de generer un ticket de mouture unique.")
