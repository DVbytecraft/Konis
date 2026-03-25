"""
Services usine KONIS : creation de lots, transferts vers boutiques.
Transactions atomiques.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from core.models import Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock, transfert_entre_usines, transfert_usine_vers_boutique
from produits.models import Produit
from usine.models import LotProduction, TransfertCession, TransfertInterUsine


def creer_lot_production(
    *,
    lieu_usine: Lieu,
    produit_fini: Produit,
    nom_lot: str,
    quantite_sacs: Decimal,
    poids: Decimal = Decimal("0"),
    unite_poids: str = "kg",
    created_by=None,
) -> LotProduction:
    """
    Cree un lot de production et credite le stock produit fini a l'usine.
    """
    if lieu_usine.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock("Le lieu doit etre une usine.")
    if quantite_sacs <= 0:
        raise ErreurStock("La quantite de sacs produits doit etre > 0.")
    if poids < 0:
        raise ErreurStock("Le poids doit etre >= 0.")
    if not nom_lot or not nom_lot.strip():
        raise ErreurStock("La reference du lot est obligatoire.")

    with transaction.atomic():
        lot = LotProduction.objects.create(
            nom_lot=nom_lot.strip(),
            lieu_usine=lieu_usine,
            produit_fini=produit_fini,
            quantite_sacs=quantite_sacs,
            poids=poids,
            unite_poids=unite_poids,
            created_by=created_by,
        )
        # Crediter le stock produit fini a l'usine.
        # get_or_create d'abord (sans lock), puis SELECT FOR UPDATE sur pk existant.
        # select_for_update().get_or_create() est unsafe : le INSERT interne
        # ignore le lock et provoque des deadlocks sous charge.
        stock_fini, _ = Stock.objects.get_or_create(
            produit=produit_fini,
            lieu=lieu_usine,
            defaults={"quantite": Decimal("0")},
        )
        stock_fini = Stock.objects.select_for_update().get(pk=stock_fini.pk)
        stock_fini.quantite += quantite_sacs
        stock_fini.save(update_fields=["quantite", "updated_at"])

    return lot


def transferer_lot_vers_boutique(
    *,
    lot: LotProduction,
    boutique: Lieu,
    quantite_sacs: Decimal,
    poids_total: Decimal = Decimal("0"),
    prix_par_sac: Decimal,
) -> TransfertCession:
    """
    Transfere une quantite de sacs du stock usine vers une boutique.
    Cree un TransfertCession et met a jour les stocks.
    """
    if lot.lieu_usine.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock("Le lot n'est pas rattache a une usine.")
    if boutique.type_lieu != Lieu.TYPE_MAGASIN:
        raise ErreurStock("La destination doit etre une boutique.")
    if lot.lieu_usine.entreprise_id != boutique.entreprise_id:
        raise ErreurStock("Transfert inter-entreprises interdit.")
    if quantite_sacs <= 0:
        raise ErreurStock("Quantite de cession invalide.")
    if prix_par_sac < 0:
        raise ErreurStock("Prix par sac invalide.")

    with transaction.atomic():
        transfert = transfert_usine_vers_boutique(
            lot.lieu_usine,
            boutique,
            [(lot.produit_fini, quantite_sacs, prix_par_sac, lot)],
        )
        cession = TransfertCession.objects.create(
            lot=lot,
            boutique=boutique,
            quantite_sacs=quantite_sacs,
            poids_total=poids_total,
            prix_par_sac=prix_par_sac,
            transfert=transfert,
        )
    return cession


def transferer_lot_vers_usine(
    *,
    lot: LotProduction,
    usine_destination: Lieu,
    quantite_sacs: Decimal,
    poids_total: Decimal = Decimal("0"),
    prix_par_sac: Decimal = Decimal("0"),
    notes: str = "",
    created_by=None,
) -> TransfertInterUsine:
    """
    Transfere une quantite de sacs du stock d'une usine vers une autre usine.
    Cree un TransfertInterUsine et met a jour les stocks.
    """
    if lot.lieu_usine.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock("Le lot n'est pas rattache a une usine.")
    if usine_destination.type_lieu != Lieu.TYPE_USINE:
        raise ErreurStock("La destination doit etre une usine.")
    if lot.lieu_usine.entreprise_id != usine_destination.entreprise_id:
        raise ErreurStock("Transfert inter-entreprises interdit.")
    if lot.lieu_usine == usine_destination:
        raise ErreurStock("L'usine source et de destination doivent etre differentes.")
    if quantite_sacs <= 0:
        raise ErreurStock("Quantite de transfert invalide.")
    if prix_par_sac < 0:
        raise ErreurStock("Prix par sac invalide.")

    with transaction.atomic():
        transfert = transfert_entre_usines(
            lot.lieu_usine,
            usine_destination,
            [(lot.produit_fini, quantite_sacs, prix_par_sac, lot)],
        )
        inter_usine = TransfertInterUsine.objects.create(
            lot=lot,
            usine_destination=usine_destination,
            quantite_sacs=quantite_sacs,
            poids_total=poids_total,
            prix_par_sac=prix_par_sac,
            notes=notes,
            created_by=created_by,
            transfert=transfert,
        )
    return inter_usine
