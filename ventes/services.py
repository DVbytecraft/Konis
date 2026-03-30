"""
Services ventes KONIS : vente boutique, numéro de ticket automatique.
Transaction atomique. Historique via Ticket + LigneVente.

Mouture — formule unifiée (toutes unités normalisées en kg) :
    quantite_kg_total = normaliser_quantite_en_kg(apportée) + normaliser_quantite_en_kg(achetée)
    cout_mouture      = calculer_cout_mouture(quantite_kg_total, prix_par_kg)
    montant_total     = products_total + cout_mouture

Type de vente :
    cash    → montant_cash = montant_total, montant_credit = 0, pas de JournalCreance
    credit  → montant_cash = 0, montant_credit = montant_total, JournalCreance auto-créé
    partiel → montant_cash = acompte, montant_credit = montant_total - acompte, JournalCreance pour le solde
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Lieu
from inventaire.models import Stock
from inventaire.services import ErreurStock, _prelever_stock_unite, _verifier_stock_disponible
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
    if u in ("tonne", "tonnes"):
        return quantite * KG_PAR_TONNE
    if u in ("sac", "sacs"):
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
    lignes: list[tuple],
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
        (quantite * prix_unitaire for _, quantite, prix_unitaire, *_ in lignes),
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
    for line in lignes:
        produit, quantite, _ = line[0], line[1], line[2]
        unite_ligne = line[3] if len(line) > 3 and line[3] else (produit.unite or "kg")
        qty_produits_kg += normaliser_quantite_en_kg(
            quantite, unite_ligne, produit
        )

    total_mouture_kg = qty_produits_kg + quantite_apportee_client_kg
    cout_mouture = calculer_cout_mouture(total_mouture_kg, prix_mouture_kg)

    return montant_produits, cout_mouture, montant_produits + cout_mouture


# ── Helpers pré-vente (extraits de la vue pour testabilité) ─────────────────

def preparer_lignes_vente(lieu: Lieu, lignes_data: list) -> list:
    """
    Charge les produits en 1 requête, valide l'appartenance à l'entreprise et
    les unités, retourne une liste de tuples (produit, quantite, prix_unitaire, unite).
    Lève ErreurStock si un produit est inconnu/non autorisé ou si l'unité est invalide.
    """
    produit_ids = [
        item["produit"] if isinstance(item["produit"], int) else item["produit"].pk
        for item in lignes_data
    ]
    produits_map = {
        p.pk: p
        for p in Produit.objects.filter(pk__in=produit_ids, entreprise=lieu.entreprise)
    }
    lignes = []
    for item in lignes_data:
        produit_id = item["produit"] if isinstance(item["produit"], int) else item["produit"].pk
        produit = produits_map.get(produit_id)
        if produit is None:
            raise ErreurStock(f"Produit inconnu ou non autorisé : {produit_id}")
        quantite = Decimal(str(item["quantite"]))
        prix_unitaire = Decimal(str(item["prix_unitaire"]))
        raw_unite = (item.get("unite") or "").strip().lower()
        if raw_unite:
            if raw_unite not in ("kg", "sac", "sacs"):
                raise ErreurStock(f"Unité invalide pour {produit.nom} : '{raw_unite}'.")
            unite_ligne = "sac" if raw_unite in ("sac", "sacs") else "kg"
        else:
            unite_ligne = produit.unite or "kg"
        lignes.append((produit, quantite, prix_unitaire, unite_ligne))
    return lignes


def valider_prix_mouture(lieu: Lieu, prix_mouture_kg) -> None:
    """
    Vérifie que le prix mouture ne dépasse pas le plafond configuré sur le lieu.
    Lève ErreurStock si le plafond est dépassé.
    """
    if prix_mouture_kg and lieu.prix_mouture_max and prix_mouture_kg > lieu.prix_mouture_max:
        raise ErreurStock(
            f"Prix mouture {prix_mouture_kg} FCFA/kg dépasse le plafond autorisé "
            f"({lieu.prix_mouture_max} FCFA/kg). Contactez l'administrateur."
        )


def preparer_mouture_vente(lieu: Lieu, ser_data: dict) -> Decimal:
    """
    Normalise la quantité de grain apportée par le client en kg.
    Valide le produit apporté contre l'entreprise du lieu.
    Lève ErreurStock si la conversion est impossible ou le produit introuvable.
    """
    qty_apportee = ser_data.get("quantite_apportee_mouture") or Decimal("0")
    if qty_apportee <= 0:
        return Decimal("0")
    unite_apportee = ser_data.get("unite_apportee_mouture", "kg")
    produit_ref = None
    produit_id_apportee = ser_data.get("produit_id_apportee")
    if produit_id_apportee:
        try:
            produit_ref = Produit.objects.get(pk=produit_id_apportee, entreprise=lieu.entreprise)
        except Produit.DoesNotExist:
            raise ErreurStock(f"Produit apportée {produit_id_apportee} introuvable.")
    return normaliser_quantite_en_kg(qty_apportee, unite_apportee, produit_ref)


def charger_client_vente(lieu: Lieu, client_id):
    """
    Charge un ClientFinance scopé à l'entreprise du lieu.
    Retourne None si client_id est absent.
    Lève ErreurStock si le client est introuvable ou non autorisé.
    """
    if not client_id:
        return None
    from finance.models import ClientFinance
    try:
        return ClientFinance.objects.get(pk=client_id, entreprise_id=lieu.entreprise_id)
    except ClientFinance.DoesNotExist:
        raise ErreurStock("Client introuvable ou non autorisé.")


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

def _creer_journal_creance_pour_ticket(ticket: Ticket, montant: Decimal, created_by) -> None:
    """
    Crée automatiquement un JournalCreance lié à un ticket de vente à crédit/partiel.
    Appelé à l'intérieur d'une transaction atomique.
    """
    from finance.models import ClientFinance, JournalCreance

    if ticket.client_id is None:
        raise ErreurStock(
            "Un client est requis pour une vente à crédit ou partielle."
        )
    if montant <= Decimal("0"):
        return  # rien à créer

    # Évite le double-create si le ticket a déjà une créance (idempotency replay)
    if hasattr(ticket, "creance"):
        return

    JournalCreance.objects.create(
        client_id=ticket.client_id,
        lieu=ticket.lieu,
        ticket=ticket,
        reference=ticket.numero,
        description=f"Vente à crédit — ticket {ticket.numero}",
        montant_initial=montant,
        created_by=created_by,
    )


def vente_boutique(
    lieu: Lieu,
    lignes: list[tuple],
    *,
    mouture: bool = False,
    prix_mouture_kg: Decimal | None = None,
    quantite_apportee_client_kg: Decimal = Decimal("0"),
    idempotency_key: str | None = None,
    type_vente: str = Ticket.TYPE_CASH,
    montant_cash: Decimal | None = None,
    client=None,
    created_by=None,
) -> tuple[Ticket, bool]:
    """
    Enregistre une vente en boutique (ticket + lignes + mouture optionnelle).
    Transaction atomique. Numéro de ticket généré automatiquement.
    Lève ErreurStock si stock insuffisant.

    Retourne (ticket, created) :
      created=False si un ticket existant avec la même clé idempotency a été renvoyé.

    lignes          : liste de (produit, quantite, prix_unitaire, unite?)
    mouture         : True si le client demande la mouture
    prix_mouture_kg : prix FCFA/kg (toutes unités normalisées en kg avant calcul)
    quantite_apportee_client_kg : grain supplémentaire apporté par le client (déjà en kg)
    idempotency_key : clé de déduplication (header Idempotency-Key du client)
    type_vente      : 'cash' | 'credit' | 'partiel'
    montant_cash    : acompte si type_vente='partiel' (None = montant total si cash)
    client          : ClientFinance requis si credit ou partiel
    created_by      : CustomUser pour l'audit JournalCreance
    """
    # ── Validation type_vente ────────────────────────────────────────────────
    if type_vente not in (Ticket.TYPE_CASH, Ticket.TYPE_CREDIT, Ticket.TYPE_PARTIEL):
        raise ErreurStock(f"type_vente invalide : '{type_vente}'.")
    if type_vente in (Ticket.TYPE_CREDIT, Ticket.TYPE_PARTIEL) and client is None:
        raise ErreurStock("Un client est requis pour une vente à crédit ou partielle.")
    if type_vente == Ticket.TYPE_PARTIEL:
        if montant_cash is None or montant_cash < Decimal("0"):
            raise ErreurStock("montant_cash (acompte) est requis et doit être >= 0 pour une vente partielle.")

    key = (idempotency_key or "").strip() or None
    if lieu.type_lieu != Lieu.TYPE_MAGASIN:
        raise ErreurStock(f"Le lieu {lieu} n'est pas un magasin.")

    with transaction.atomic():
        # Déduplication INSIDE la transaction (même pattern que vente_mouture_seule).
        # select_for_update sérialise les requêtes concurrentes sur le même lieu/clé
        # et évite le TOCTOU entre le check et le create.
        if key:
            existing = (
                Ticket.objects.select_for_update()
                .filter(lieu=lieu, idempotency_key=key, mouture=mouture)
                .first()
            )
            if existing is not None:
                return existing, False

        # Verrouiller et vérifier les stocks
        for line in lignes:
            produit, quantite = line[0], line[1]
            unite_ligne = line[3] if len(line) > 3 and line[3] else (produit.unite or "kg")
            if quantite <= 0:
                raise ErreurStock(f"Quantité invalide pour {produit}: {quantite}")
            try:
                stock = Stock.objects.select_for_update().get(
                    produit=produit, lieu=lieu
                )
            except Stock.DoesNotExist:
                raise ErreurStock(f"Pas de stock pour {produit} à {lieu}.")
            _verifier_stock_disponible(stock, quantite, unite_ligne)

        montant_produits, cout_mouture, montant_total = _compute_boutique_totals(
            lignes,
            mouture=mouture,
            prix_mouture_kg=prix_mouture_kg,
            quantite_apportee_client_kg=quantite_apportee_client_kg,
        )

        # ── Calculer répartition cash / crédit ──────────────────────────────
        if type_vente == Ticket.TYPE_CASH:
            m_cash   = montant_total
            m_credit = Decimal("0")
        elif type_vente == Ticket.TYPE_CREDIT:
            m_cash   = Decimal("0")
            m_credit = montant_total
        else:  # partiel
            m_cash   = montant_cash  # type: ignore[assignment]
            m_credit = montant_total - m_cash
            if m_credit < Decimal("0"):
                raise ErreurStock(
                    f"L'acompte ({m_cash}) dépasse le montant total ({montant_total})."
                )

        ticket = None
        for _ in range(5):
            numero = generer_numero_ticket(lieu)
            try:
                # Savepoint isolé : un IntegrityError ici ne corrompt pas la
                # transaction parente (PostgreSQL annule uniquement le savepoint).
                # Sans ce bloc, IntegrityError aborderait la transaction entière et
                # toute requête suivante lèverait TransactionManagementError.
                with transaction.atomic():
                    ticket = Ticket.objects.create(
                        lieu=lieu,
                        numero=numero,
                        mouture=mouture,
                        prix_mouture_kg=prix_mouture_kg if mouture else None,
                        cout_mouture=cout_mouture,
                        montant_total=montant_total,
                        quantite_apportee_client=quantite_apportee_client_kg if mouture else Decimal("0"),
                        idempotency_key=key,
                        type_vente=type_vente,
                        montant_cash=m_cash,
                        montant_credit=m_credit,
                        client=client,
                    )
                break
            except IntegrityError:
                # Collision de numéro de ticket OU de clé idempotency.
                # La transaction parente est intacte (seul le savepoint a été annulé)
                # → on peut interroger la DB normalement.
                if key:
                    existing = Ticket.objects.filter(
                        lieu=lieu, idempotency_key=key, mouture=mouture
                    ).first()
                    if existing is not None:
                        return existing, False
                continue
        if ticket is None:
            raise ErreurStock("Impossible de generer un numero de ticket unique.")

        for line in lignes:
            produit, quantite, prix_unitaire = line[0], line[1], line[2]
            unite_ligne = line[3] if len(line) > 3 and line[3] else (produit.unite or "kg")
            LigneVente.objects.create(
                ticket=ticket,
                produit=produit,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
                unite=unite_ligne,
            )
            _prelever_stock_unite(
                stock=Stock.objects.get(produit=produit, lieu=lieu),
                quantite=quantite,
                unite=unite_ligne,
                updated_by=created_by,
            )

        # ── Auto-créer JournalCreance si crédit ou partiel ──────────────────
        if type_vente in (Ticket.TYPE_CREDIT, Ticket.TYPE_PARTIEL) and m_credit > Decimal("0"):
            _creer_journal_creance_pour_ticket(ticket, m_credit, created_by)

    return ticket, True


def vente_mouture_seule(
    lieu: Lieu,
    quantite_apportee: Decimal,
    quantite_achetee: Decimal,
    unite: str,
    prix_par_kg: Decimal,
    produit_apporte: str = "",
    produit_ref: Produit | None = None,
    idempotency_key: str | None = None,
    nombre_sacs: int | None = None,
    poids_par_sac: Decimal | None = None,
    type_mouture: str = Ticket.TYPE_MOUTURE_CLIENT,
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
                with transaction.atomic():
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
                        montant_cash=cout,      # mouture = toujours cash
                        montant_credit=Decimal("0"),
                        nombre_sacs=nombre_sacs,
                        poids_par_sac=poids_par_sac,
                        type_mouture=type_mouture,
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
