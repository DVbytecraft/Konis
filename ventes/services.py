"""
Services ventes KONIS : vente boutique, numéro de ticket automatique.
Transaction atomique. Historique via Ticket + LigneVente.

Mouture — formule unifiée (toutes unités normalisées en kg) :
    quantite_kg_total = normaliser_quantite_en_kg(apportée) + normaliser_quantite_en_kg(achetée)
    cout_mouture      = calculer_cout_mouture(quantite_kg_total, prix_par_kg)
    montant_total     = products_total + cout_mouture
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock
from produits.models import Produit
from ventes.models import LigneVente, Ticket

# ── Constantes de conversion ────────────────────────────────────────────────
KG_PAR_TONNE = Decimal("1000")


# ── Fonctions centralisées mouture ──────────────────────────────────────────

def normaliser_quantite_en_kg(
    quantite: Decimal,
    unite: str,
    produit: Produit | None = None,
) -> Decimal:
    """
    Convertit n'importe quelle quantité vers kg — unité interne unique.

    unite : 'kg' | 'tonne' | 'sac'
    produit : requis si unite='sac' (utilise produit.poids_par_sac)

    Lève ErreurStock si la conversion est impossible.
    """
    u = (unite or "").strip().lower()
    if u == "kg":
        return quantite
    if u == "tonne":
        return quantite * KG_PAR_TONNE
    if u == "sac":
        if produit is None or produit.poids_par_sac is None:
            nom = getattr(produit, "nom", "inconnu") if produit else "inconnu"
            raise ErreurStock(
                f"Mouture en sacs: poids_par_sac non défini pour le produit '{nom}'. "
                "Configurez le poids par sac dans la fiche produit (administration)."
            )
        return quantite * produit.poids_par_sac
    raise ErreurStock(
        f"Unité mouture non supportée: '{unite}'. Utiliser kg, tonne ou sac."
    )


def calculer_cout_mouture(quantite_kg: Decimal, prix_par_kg: Decimal) -> Decimal:
    """
    Source unique de vérité pour le coût mouture.
    Formule : cout = quantite_kg × prix_par_kg  (arrondi à 2 décimales).
    """
    return (quantite_kg * prix_par_kg).quantize(Decimal("0.01"))


# ── Calcul totaux boutique ──────────────────────────────────────────────────

def _compute_boutique_totals(
    lignes: list[tuple[Produit, Decimal, Decimal]],
    *,
    mouture: bool,
    prix_mouture_kg: Decimal | None,
    quantite_apportee_client_kg: Decimal = Decimal("0"),
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Source unique de vérité pour les totaux d'une vente boutique.

    Formule unifiée (mouture=True) :
        qty_produits_kg  = Σ normaliser_quantite_en_kg(ligne.quantite, produit.unite, produit)
        total_mouture_kg = qty_produits_kg + quantite_apportee_client_kg
        cout_mouture     = calculer_cout_mouture(total_mouture_kg, prix_mouture_kg)
        montant_total    = montant_produits + cout_mouture

    Retourne (montant_produits, cout_mouture, montant_total).
    """
    montant_produits = sum(
        (quantite * prix_unitaire for _, quantite, prix_unitaire in lignes),
        Decimal("0"),
    )

    if not mouture:
        return montant_produits, Decimal("0"), montant_produits

    if prix_mouture_kg is None:
        raise ErreurStock(
            "Mouture demandée : prix_mouture_kg (FCFA/kg) est requis. "
            "Toutes les unités sont normalisées en kg avant calcul."
        )

    # Normaliser toutes les lignes produits en kg
    qty_produits_kg = Decimal("0")
    for produit, quantite, _ in lignes:
        qty_produits_kg += normaliser_quantite_en_kg(
            quantite, produit.unite or "kg", produit
        )

    total_mouture_kg = qty_produits_kg + quantite_apportee_client_kg
    cout_mouture = calculer_cout_mouture(total_mouture_kg, prix_mouture_kg)

    return montant_produits, cout_mouture, montant_produits + cout_mouture


# ── Numéro de ticket ────────────────────────────────────────────────────────

def generer_numero_ticket(lieu: Lieu) -> str:
    """
    Génère le prochain numéro de ticket pour un lieu (séquence par jour).
    Format : KONIS-{CODE_LIEU}-{YYYYMMDD}-{SEQ:06d}
    Exemple : KONIS-CENTRE-20260208-000123
    Unicité garantie par verrouillage du lieu (select_for_update) dans la transaction.
    """
    today = timezone.now().date()
    Lieu.objects.select_for_update().get(pk=lieu.pk)
    count = Ticket.objects.filter(lieu=lieu, date__date=today).count()
    seq = count + 1
    code = (lieu.code or "").strip().upper() or f"L{lieu.id}"
    code = "".join(c for c in code if c.isalnum())[:10] or f"L{lieu.id}"
    return f"KONIS-{code}-{today:%Y%m%d}-{seq:06d}"


# ── Vente boutique (avec ou sans mouture) ───────────────────────────────────

def vente_boutique(
    lieu: Lieu,
    lignes: list[tuple[Produit, Decimal, Decimal]],
    *,
    mouture: bool = False,
    prix_mouture_kg: Decimal | None = None,
    quantite_apportee_client_kg: Decimal = Decimal("0"),
) -> Ticket:
    """
    Enregistre une vente en boutique (ticket + lignes + mouture optionnelle).
    Transaction atomique. Numéro de ticket généré automatiquement.
    Lève ErreurStock si stock insuffisant.

    lignes : liste de (produit, quantite, prix_unitaire)
    mouture : True si le client demande la mouture
    prix_mouture_kg : prix FCFA/kg (toutes unités normalisées en kg avant calcul)
    quantite_apportee_client_kg : grain supplémentaire apporté par le client (déjà en kg)
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
            quantite_apportee_client_kg=quantite_apportee_client_kg,
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
                    cout_mouture=cout_mouture,
                    montant_total=montant_total,
                    quantite_apportee_client=quantite_apportee_client_kg if mouture else Decimal("0"),
                )
                break
            except IntegrityError:
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
            stock = Stock.objects.select_for_update().get(produit=produit, lieu=lieu)
            stock.quantite -= quantite
            stock.save(update_fields=["quantite"])

    return ticket


# ── Mouture seule (sans vente de produits) ───────────────────────────────────

def vente_mouture_seule(
    lieu: Lieu,
    quantite_apportee: Decimal,
    quantite_achetee: Decimal,
    unite: str,
    prix_par_kg: Decimal,
    produit_apporte: str = "",
    produit_ref: Produit | None = None,
    idempotency_key: str | None = None,
) -> tuple[Ticket, bool]:
    """
    Ticket mouture-seule : aucune déduction de stock.
    Gère 3 sous-scénarios :
      1. Mouture seule   — quantite_achetee=0, grain apporté uniquement
      2. Mouture étendue — grain apporté + grain acheté (hors stock)
      3. Replay idempotent — même clé → retourne le ticket existant

    Formule unifiée :
        apportee_kg = normaliser_quantite_en_kg(quantite_apportee, unite, produit_ref)
        achetee_kg  = normaliser_quantite_en_kg(quantite_achetee,  unite, produit_ref)
        total_kg    = apportee_kg + achetee_kg
        cout        = calculer_cout_mouture(total_kg, prix_par_kg)

    Retourne (ticket, created). created=False → replay idempotent.
    """
    apportee_kg = normaliser_quantite_en_kg(quantite_apportee, unite, produit_ref)
    achetee_kg = normaliser_quantite_en_kg(quantite_achetee, unite, produit_ref)
    total_kg = apportee_kg + achetee_kg

    if total_kg <= Decimal("0"):
        raise ErreurStock("La quantité totale à moudre doit être supérieure à 0.")

    cout = calculer_cout_mouture(total_kg, prix_par_kg)
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
                    prix_mouture_kg=prix_par_kg,
                    quantite_apportee_client=apportee_kg,
                    cout_mouture=cout,
                    montant_total=cout,
                )
                return ticket, True
            except IntegrityError:
                if key:
                    existing = Ticket.objects.filter(
                        lieu=lieu, idempotency_key=key, mouture=True,
                    ).first()
                    if existing is not None:
                        return existing, False
                continue

    raise ErreurStock("Impossible de generer un ticket de mouture unique.")
