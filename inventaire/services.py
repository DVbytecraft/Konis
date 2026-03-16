"""
Services inventaire KONIS : transferts de stock et achats.
Transactions atomiques. Historique via Transfert/MouvementStock.
"""
from decimal import Decimal

from django.db import transaction

from core.models import Lieu
from inventaire.models import AchatMPSL, AchatUsine, MouvementStock, Stock, Transfert


class ErreurStock(Exception):
    """Erreur métier (ex. stock insuffisant)."""


# ─── Achat usine (comptable uniquement) ───────────────────────────────────────

def enregistrer_achat_usine(
    lieu: Lieu,
    produit_nom: str,
    quantite: Decimal,
    unite: str,
    prix_unitaire: Decimal = Decimal("0"),
    notes: str = "",
    created_by=None,
) -> AchatUsine:
    """
    Enregistre un achat d'intrant à l'usine (enregistrement comptable uniquement).
    NE modifie PAS le stock — le stock est géré via LotProduction.
    """
    if lieu.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock(f"Le lieu {lieu} n'est pas une usine.")
    if not produit_nom or not produit_nom.strip():
        raise ErreurStock("Le nom du produit acheté est obligatoire.")
    if quantite <= 0:
        raise ErreurStock("La quantité doit être strictement positive.")
    if prix_unitaire < 0:
        raise ErreurStock("Le prix unitaire doit être >= 0.")

    prix_total = Decimal(str(quantite)) * Decimal(str(prix_unitaire))

    return AchatUsine.objects.create(
        lieu=lieu,
        produit_nom=produit_nom.strip(),
        quantite=quantite,
        unite=unite,
        prix_unitaire=prix_unitaire,
        prix_total=prix_total,
        notes=notes or "",
        created_by=created_by,
    )


# ─── Achat MPSL (avec impact stock) ───────────────────────────────────────────

def enregistrer_achat_mpsl(
    lieu: Lieu,
    produit,
    quantite: Decimal,
    unite: str,
    prix_unitaire: Decimal = Decimal("0"),
    notes: str = "",
    created_by=None,
) -> AchatMPSL:
    """
    Enregistre un achat de produit au dépôt MPSL.
    IMPACTE le stock : ajoute la quantité au stock du dépôt MPSL.
    Flux : Fournisseur → MPSL (avec prix d'achat).
    """
    if lieu.type_lieu != Lieu.TYPE_MPSL:
        raise ErreurStock(f"Le lieu '{lieu}' n'est pas un dépôt MPSL.")
    if quantite <= 0:
        raise ErreurStock("La quantité doit être strictement positive.")
    if prix_unitaire < 0:
        raise ErreurStock("Le prix unitaire doit être >= 0.")
    if produit.entreprise_id != lieu.entreprise_id:
        raise ErreurStock("Le produit et le dépôt doivent appartenir à la même entreprise.")

    prix_total = Decimal(str(quantite)) * Decimal(str(prix_unitaire))

    with transaction.atomic():
        achat = AchatMPSL.objects.create(
            lieu=lieu,
            produit=produit,
            quantite=quantite,
            unite=unite,
            prix_unitaire=prix_unitaire,
            prix_total=prix_total,
            notes=notes or "",
            created_by=created_by,
        )
        # Créditer le stock du dépôt MPSL
        stock, created = Stock.objects.select_for_update().get_or_create(
            produit=produit,
            lieu=lieu,
            defaults={"quantite": Decimal("0")},
        )
        stock.quantite += quantite
        stock.save(update_fields=["quantite"])

    return achat


# ─── Noyau commun des transferts ──────────────────────────────────────────────

def _noyau_transfert(
    from_lieu: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
) -> Transfert:
    """
    Exécute un transfert de stock de manière atomique.
    Les validations métier (types de lieux, etc.) sont effectuées par les fonctions appelantes.

    lignes accepte des tuples :
      (produit, quantite)
      (produit, quantite, unit_price)
      (produit, quantite, unit_price, production_order)
    """
    with transaction.atomic():
        # Validation + verrouillage préalable de toutes les lignes
        normalized: list[tuple] = []
        for line in lignes:
            produit = line[0]
            quantite = Decimal(str(line[1]))
            unit_price = Decimal(str(line[2])) if len(line) > 2 else Decimal("0")
            production_order = line[3] if len(line) > 3 else None

            if quantite <= 0:
                raise ErreurStock(f"Quantité invalide pour {produit} : {quantite}.")
            if unit_price < 0:
                raise ErreurStock(f"Prix unitaire invalide pour {produit} : {unit_price}.")

            try:
                stock = Stock.objects.select_for_update().get(produit=produit, lieu=from_lieu)
            except Stock.DoesNotExist:
                raise ErreurStock(f"Aucun stock pour '{produit}' à '{from_lieu}'.")

            if stock.quantite < quantite:
                raise ErreurStock(
                    f"Stock insuffisant pour '{produit}' à '{from_lieu}' : "
                    f"disponible {stock.quantite}, demandé {quantite}."
                )
            normalized.append((produit, quantite, unit_price, production_order))

        # Création du transfert et application des mouvements
        transfert = Transfert.objects.create(from_lieu=from_lieu, to_lieu=to_lieu)

        for produit, quantite, unit_price, production_order in normalized:
            MouvementStock.objects.create(
                transfert=transfert,
                produit=produit,
                quantite=quantite,
                unit_price=unit_price,
                production_order=production_order,
            )
            # Débit stock source
            stock_from = Stock.objects.select_for_update().get(produit=produit, lieu=from_lieu)
            stock_from.quantite -= quantite
            stock_from.save(update_fields=["quantite"])

            # Crédit stock destination (créer si absent)
            stock_to = Stock.objects.select_for_update().filter(produit=produit, lieu=to_lieu).first()
            if stock_to is None:
                Stock.objects.create(produit=produit, lieu=to_lieu, quantite=quantite)
            else:
                stock_to.quantite += quantite
                stock_to.save(update_fields=["quantite"])

    return transfert


# ─── Transferts usine (existants) ─────────────────────────────────────────────

def _executer_transfert(
    from_lieu: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
    type_destination: str,
) -> Transfert:
    """
    Noyau commun des transferts de stock (usine→boutique et usine→usine).
    Conservé pour compatibilité avec usine/services.py.
    """
    if from_lieu.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock(f"Le lieu d'origine '{from_lieu}' n'est pas une usine.")
    if to_lieu.type_lieu != type_destination:
        label = "un magasin" if type_destination == Lieu.TYPE_MAGASIN else "une usine"
        raise ErreurStock(f"Le lieu de destination '{to_lieu}' n'est pas {label}.")
    if from_lieu.entreprise_id != to_lieu.entreprise_id:
        raise ErreurStock("Transfert inter-entreprises interdit.")
    if from_lieu == to_lieu:
        raise ErreurStock("Origine et destination doivent être différents.")
    return _noyau_transfert(from_lieu, to_lieu, lignes)


def transfert_usine_vers_boutique(
    from_lieu: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
) -> Transfert:
    """Transfère du stock d'une usine vers une boutique (magasin)."""
    return _executer_transfert(from_lieu, to_lieu, lignes, Lieu.TYPE_MAGASIN)


def transfert_entre_usines(
    from_lieu: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
) -> Transfert:
    """Transfère du stock d'une usine vers une autre usine."""
    return _executer_transfert(from_lieu, to_lieu, lignes, Lieu.TYPE_USINE)


# ─── Transferts MPSL ──────────────────────────────────────────────────────────

def transfert_depuis_mpsl(
    from_mpsl: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
) -> Transfert:
    """
    Transfère du stock depuis un dépôt MPSL vers une usine ou un magasin.
    Transfert pur : pas de prix (unit_price=0), pas de vente, pas d'achat.
    Destinations autorisées : usine ou magasin.
    """
    if from_mpsl.type_lieu != Lieu.TYPE_MPSL:
        raise ErreurStock(f"Le lieu source '{from_mpsl}' n'est pas un dépôt MPSL.")
    if to_lieu.type_lieu not in (Lieu.TYPE_USINE, Lieu.TYPE_MAGASIN):
        raise ErreurStock(
            f"La destination '{to_lieu}' doit être une usine ou un magasin."
        )
    if from_mpsl.entreprise_id != to_lieu.entreprise_id:
        raise ErreurStock("Transfert inter-entreprises interdit.")
    if from_mpsl.id == to_lieu.id:
        raise ErreurStock("Origine et destination doivent être différents.")
    # Les transferts MPSL n'ont pas de prix — forcer unit_price à 0
    lignes_sans_prix = [
        (line[0], line[1], Decimal("0")) for line in lignes
    ]
    return _noyau_transfert(from_mpsl, to_lieu, lignes_sans_prix)


# ─── Transferts directs usine (sans LotProduction) ────────────────────────────

def transfert_direct_usine_vers(
    from_usine: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
) -> Transfert:
    """
    Transfère du stock depuis une usine vers une autre usine ou un magasin,
    sans passer par un LotProduction.
    Transfert pur : pas de prix (unit_price=0).
    Destinations autorisées : usine ou magasin.
    """
    if from_usine.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock(f"Le lieu source '{from_usine}' n'est pas une usine.")
    if to_lieu.type_lieu not in (Lieu.TYPE_USINE, Lieu.TYPE_MAGASIN):
        raise ErreurStock(
            f"La destination '{to_lieu}' doit être une usine ou un magasin."
        )
    if from_usine.entreprise_id != to_lieu.entreprise_id:
        raise ErreurStock("Transfert inter-entreprises interdit.")
    if from_usine.id == to_lieu.id:
        raise ErreurStock("Origine et destination doivent être différents.")
    # Les transferts directs n'ont pas de prix — forcer unit_price à 0
    lignes_sans_prix = [
        (line[0], line[1], Decimal("0")) for line in lignes
    ]
    return _noyau_transfert(from_usine, to_lieu, lignes_sans_prix)
