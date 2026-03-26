"""
Services inventaire KONIS : transferts de stock et achats.
Transactions atomiques. Historique via Transfert/MouvementStock.
"""
import logging
from decimal import Decimal, ROUND_CEILING

from django.db import transaction

_alert = logging.getLogger("konis.alerts")

from core.models import Lieu
from inventaire.models import AchatMPSL, AchatUsine, MouvementStock, Stock, Transfert
from produits.models import Produit


class ErreurStock(Exception):
    """Erreur métier (ex. stock insuffisant)."""
# ---- Helpers unités & stock -------------------------------------------------

def _normaliser_unite_stock(unite: str | None) -> str:
    u = (unite or "").strip().lower()
    if u in ("sac", "sacs"):
        return "sac"
    if u in ("kg", "kilogramme", "kilogrammes"):
        return "kg"
    if u in ("tonne", "tonnes", "t"):
        return "tonne"
    return u


def _kg_depuis_unite(quantite: Decimal, unite: str) -> Decimal:
    if unite == "kg":
        return quantite
    if unite == "tonne":
        return quantite * Decimal("1000")
    raise ErreurStock(f"Unité non supportée pour conversion kg : '{unite}'.")


def get_quantite_equivalente_kg(stock: Stock) -> Decimal:
    """
    Retourne la quantité totale en kg pour un stock donné.
    - Si poids_par_sac défini : quantite_kg + (quantite_sac × poids_par_sac)
    - Sinon : quantite_kg si > 0, sinon quantite (supposée déjà en kg)
    """
    if stock is None:
        return Decimal("0")
    q_sac = stock.quantite or Decimal("0")
    q_kg = stock.quantite_kg or Decimal("0")
    pps = getattr(stock.produit, "poids_par_sac", None)
    if pps:
        return q_kg + (q_sac * pps)
    return q_kg if q_kg > 0 else q_sac


def _verifier_stock_disponible(stock: Stock, quantite: Decimal, unite: str) -> None:
    """
    Vérifie si le stock permet de prélever quantite dans l'unité demandée.
    Lève ErreurStock si insuffisant.
    """
    u = _normaliser_unite_stock(unite)
    if u == "tonne":
        quantite = _kg_depuis_unite(quantite, "tonne")
        u = "kg"
    if quantite <= 0:
        raise ErreurStock("La quantité doit être > 0.")
    if u == "sac":
        if stock.quantite < quantite:
            raise ErreurStock(
                f"Stock insuffisant : {stock.quantite} sac(s) disponible(s), "
                f"demande {quantite}."
            )
        return
    if u == "kg":
        pps = stock.produit.poids_par_sac
        if not pps:
            # Produit en kg (pas de sacs) : utiliser le stock kg direct.
            stock_kg = stock.quantite_kg if stock.quantite_kg > 0 else stock.quantite
            if stock_kg < quantite:
                raise ErreurStock(
                    f"Stock insuffisant : {stock_kg} kg disponible(s), demande {quantite}."
                )
            return
        if stock.quantite_kg >= quantite:
            return
        kg_total = stock.quantite_kg + (stock.quantite * pps)
        if kg_total < quantite:
            raise ErreurStock(
                f"Stock insuffisant : {kg_total} kg disponible(s), demande {quantite}."
            )
        return
    if stock.quantite < quantite:
        raise ErreurStock(
            f"Stock insuffisant : {stock.quantite} disponible(s), demande {quantite}."
        )
    return


def _valider_unite_transfert(produit, unite: str, lieu) -> None:
    """
    Valide que l'unité de transfert est compatible avec l'unité native du produit.

    Règle métier :
      - Produit enregistré en 'sac' → transfert en sacs uniquement.
        Exception : si le produit a du stock kg converti (quantite_kg > 0), les
        transferts en kg sont autorisés dans la limite de ce stock converti.
      - Produit enregistré en 'kg'  → transfert en kg ou tonnes uniquement.

    Lève ErreurStock si l'unité demandée est incompatible.
    """
    unite_demandee = _normaliser_unite_stock(unite)
    produit_unite_native = _normaliser_unite_stock(getattr(produit, "unite", "kg") or "kg")

    if unite_demandee == produit_unite_native:
        return  # Unité identique — toujours autorisé
    if produit_unite_native == "kg" and unite_demandee == "tonne":
        return  # Tonne → kg : conversion automatique autorisée

    if produit_unite_native == "sac" and unite_demandee == "kg":
        # Autorisé uniquement si stock kg converti existe
        try:
            stock = Stock.objects.get(produit=produit, lieu=lieu)
            if stock.quantite_kg > 0:
                return
        except Stock.DoesNotExist:
            pass
        raise ErreurStock(
            f"'{produit.nom}' est enregistré en sacs. "
            "Convertissez des sacs en kg (via l'interface de conversion) avant de transférer en kg."
        )

    raise ErreurStock(
        f"'{produit.nom}' est enregistré en {produit_unite_native}. "
        f"Unité de transfert '{unite}' incompatible."
    )


def _prelever_stock_unite(
    stock: Stock,
    quantite: Decimal,
    unite: str,
    *,
    updated_by=None,
    log_request=None,
    action_conversion: str | None = None,
) -> dict:
    """
    Prélève le stock en respectant l'unité demandée.
    - unite='sac' : débite les sacs
    - unite='kg'  : débite les kg ; auto-convertit des sacs si nécessaire
    Retourne un dict avec les détails (kg_pris, sacs_convertis, kg_convertis).
    """
    from audit.services import audit_log

    u = _normaliser_unite_stock(unite)
    qty = Decimal(str(quantite))
    if u == "tonne":
        qty = _kg_depuis_unite(qty, "tonne")
        u = "kg"
    if qty <= 0:
        raise ErreurStock("La quantité doit être > 0.")

    locked = Stock.objects.select_for_update().get(pk=stock.pk)

    if u == "sac":
        if locked.quantite < qty:
            raise ErreurStock(
                f"Stock insuffisant : {locked.quantite} sac(s) disponible(s), "
                f"demande {qty}."
            )
        locked.quantite -= qty
        locked.save(update_fields=["quantite", "updated_at"])
        return {"kg_pris": Decimal("0"), "sacs_convertis": 0, "kg_convertis": Decimal("0")}

    if u == "kg":
        pps = locked.produit.poids_par_sac
        if not pps:
            # Produit en kg (pas de sacs) : débiter le stock kg direct.
            if locked.quantite_kg > 0:
                if locked.quantite_kg < qty:
                    raise ErreurStock(
                        f"Stock insuffisant : {locked.quantite_kg} kg disponible(s), "
                        f"demande {qty}."
                    )
                locked.quantite_kg -= qty
                locked.save(update_fields=["quantite_kg", "updated_at"])
                return {"kg_pris": qty, "sacs_convertis": 0, "kg_convertis": Decimal("0")}
            if locked.quantite < qty:
                raise ErreurStock(
                    f"Stock insuffisant : {locked.quantite} kg disponible(s), "
                    f"demande {qty}."
                )
            locked.quantite -= qty
            locked.save(update_fields=["quantite", "updated_at"])
            return {"kg_pris": qty, "sacs_convertis": 0, "kg_convertis": Decimal("0")}
        if locked.quantite_kg >= qty:
            locked.quantite_kg -= qty
            locked.save(update_fields=["quantite_kg", "updated_at"])
            return {"kg_pris": qty, "sacs_convertis": 0, "kg_convertis": Decimal("0")}

        deficit = qty - locked.quantite_kg
        sacs_needed = int((deficit / pps).to_integral_value(rounding=ROUND_CEILING))
        if Decimal(str(sacs_needed)) > locked.quantite:
            kg_total = locked.quantite_kg + (locked.quantite * pps)
            raise ErreurStock(
                f"Stock insuffisant : {kg_total} kg disponible(s), demande {qty}."
            )

        kg_convertis = Decimal(str(sacs_needed)) * pps
        locked.quantite -= Decimal(str(sacs_needed))
        locked.quantite_kg = locked.quantite_kg + kg_convertis - qty
        locked.save(update_fields=["quantite", "quantite_kg", "updated_at"])

        if sacs_needed > 0 and updated_by is not None:
            audit_log(
                user=updated_by,
                action=action_conversion or "conversion_sac_en_kg_auto",
                object_type="Stock",
                object_id=locked.pk,
                extra={
                    "lieu": locked.lieu.nom,
                    "produit": locked.produit.nom,
                    "sacs_convertis": sacs_needed,
                    "kg_convertis": str(kg_convertis),
                    "kg_preleves": str(qty),
                    "poids_par_sac": str(pps),
                },
                request=log_request,
            )
            _alert.info(
                "CONVERSION_AUTO lieu=%s produit=%s sacs=%d kg=%s",
                locked.lieu.nom, locked.produit.nom, sacs_needed, kg_convertis,
            )

        return {"kg_pris": qty, "sacs_convertis": sacs_needed, "kg_convertis": kg_convertis}

    if locked.quantite < qty:
        raise ErreurStock(
            f"Stock insuffisant : {locked.quantite} disponible(s), demande {qty}."
        )
    locked.quantite -= qty
    locked.save(update_fields=["quantite", "updated_at"])
    return {"kg_pris": Decimal("0"), "sacs_convertis": 0, "kg_convertis": Decimal("0")}


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


# ─── Achat MPSL (comptable uniquement, comme AchatUsine) ──────────────────────

def enregistrer_achat_mpsl(
    lieu: Lieu,
    produit_nom: str,
    quantite: Decimal,
    unite: str,
    prix_unitaire: Decimal = Decimal("0"),
    notes: str = "",
    created_by=None,
    fournisseur=None,
    type_paiement: str = "cash",
    montant_paye_initial: Decimal = Decimal("0"),
    poids_par_sac=None,
) -> AchatMPSL:
    """
    Enregistre un achat de produit au dépôt MPSL (enregistrement comptable).
    NE modifie PAS le stock — le MPSL est la source d'approvisionnement.
    Flux : Fournisseur → MPSL.

    Si type_paiement = 'credit' ou 'partiel' ET fournisseur fourni :
      → crée automatiquement un JournalPayable pour la dette fournisseur.
      credit  : montant_payable = prix_total
      partiel : montant_payable = prix_total - montant_paye_initial
    """
    if lieu.type_lieu != Lieu.TYPE_MPSL:
        raise ErreurStock(f"Le lieu '{lieu}' n'est pas un dépôt MPSL.")
    if not produit_nom or not produit_nom.strip():
        raise ErreurStock("Le nom du produit acheté est obligatoire.")
    if quantite <= 0:
        raise ErreurStock("La quantité doit être strictement positive.")
    if prix_unitaire < 0:
        raise ErreurStock("Le prix unitaire doit être >= 0.")
    if type_paiement not in ("cash", "credit", "partiel"):
        raise ErreurStock(f"type_paiement invalide : '{type_paiement}'.")
    if type_paiement == "partiel" and montant_paye_initial < Decimal("0"):
        raise ErreurStock("montant_paye_initial doit être >= 0.")
    # poids_par_sac est facultatif : un produit en sacs peut être enregistré sans poids.
    # Les conversions sac→kg seront indisponibles jusqu'à ce qu'il soit renseigné.

    prix_total = Decimal(str(quantite)) * Decimal(str(prix_unitaire))
    nom = produit_nom.strip()

    with transaction.atomic():
        # Synchroniser avec le catalogue INSIDE la transaction : si l'achat échoue
        # (contrainte stock, erreur), la création/mise à jour du Produit est rollbackée
        # avec lui — pas d'orphelins en base.
        existing = Produit.objects.filter(
            nom__iexact=nom,
            entreprise_id=lieu.entreprise_id,
        ).first()
        if not existing:
            unite_norm = _normaliser_unite_stock(unite)
            unite_produit = "sac" if unite_norm == "sac" else "kg" if unite_norm in ("kg", "tonne") else unite
            create_kwargs = dict(nom=nom, entreprise_id=lieu.entreprise_id, unite=unite_produit)
            if poids_par_sac is not None:
                create_kwargs["poids_par_sac"] = poids_par_sac
            existing = Produit.objects.create(**create_kwargs)
        elif poids_par_sac is not None and existing.poids_par_sac != poids_par_sac:
            existing.poids_par_sac = poids_par_sac
            existing.save(update_fields=["poids_par_sac"])

        achat = AchatMPSL.objects.create(
            lieu=lieu,
            fournisseur=fournisseur,
            produit_nom=nom,
            quantite=quantite,
            unite=unite,
            prix_unitaire=prix_unitaire,
            prix_total=prix_total,
            type_paiement=type_paiement,
            montant_paye_initial=montant_paye_initial if type_paiement == "partiel" else Decimal("0"),
            notes=notes or "",
            created_by=created_by,
        )

        # ── Auto-créer JournalPayable si crédit ou partiel + fournisseur connu ──
        # Journal = montant_initial TOTAL de l'achat ; montant_paye = acompte éventuel.
        # montant_restant = montant_initial - montant_paye = dette réelle restante.
        if type_paiement in ("credit", "partiel") and fournisseur is not None and created_by is not None:
            from finance.models import JournalPayable
            if prix_total > Decimal("0"):
                journal = JournalPayable.objects.create(
                    creancier=fournisseur,
                    reference=f"ACHAT-MPSL-{achat.pk}",
                    description=f"Achat MPSL : {nom} x {quantite} {unite}",
                    montant_initial=prix_total,
                    montant_paye=montant_paye_initial if type_paiement == "partiel" else Decimal("0"),
                    created_by=created_by,
                )
                achat.journal_payable = journal
                achat.save(update_fields=["journal_payable"])

        # ---- Mise Ã  jour stock MPSL (impact stock) ----
        u_stock = _normaliser_unite_stock(unite)
        # Étape 1 : créer si absent sans verrou — gère le cas concurrent via contrainte unique.
        # Étape 2 : verrouiller pour la mise à jour atomique.
        # NE PAS utiliser select_for_update().get_or_create() : si la ligne n'existe pas,
        # deux transactions concurrentes passent toutes deux le SELECT FOR UPDATE vide,
        # puis toutes deux tentent un INSERT → IntegrityError ou doublon selon l'isolation.
        stock, _ = Stock.objects.get_or_create(
            produit=existing,
            lieu=lieu,
            defaults={"quantite": Decimal("0")},
        )
        stock = Stock.objects.select_for_update().get(pk=stock.pk)
        if u_stock == "sac":
            stock.quantite += Decimal(str(quantite))
            stock.save(update_fields=["quantite", "updated_at"])
        elif u_stock == "kg":
            stock.quantite_kg += Decimal(str(quantite))
            stock.save(update_fields=["quantite_kg", "updated_at"])
        elif u_stock == "tonne":
            stock.quantite_kg += _kg_depuis_unite(Decimal(str(quantite)), u_stock)
            stock.save(update_fields=["quantite_kg", "updated_at"])
        else:
            raise ErreurStock(f"Unité non supportée : '{unite}'.")

    return achat


@transaction.atomic
def enregistrer_achats_mpsl_batch(
    lieu: Lieu,
    produits: list[dict],
    *,
    type_paiement: str = "cash",
    fournisseur=None,
    acompte: Decimal = Decimal("0"),
    created_by=None,
) -> list[AchatMPSL]:
    """
    Crée plusieurs AchatMPSL pour un même bon de commande.

    Un seul JournalPayable est créé pour la totalité si type_paiement ∈ {credit, partiel}.
    Chaque produit peut avoir ses propres quantite/unite/prix_unitaire/notes.

    produits : liste de dicts avec clés :
        produit_nom, quantite, unite, prix_unitaire, notes, poids_par_sac (optionnel)

    Lève ErreurStock si le lieu n'est pas MPSL ou si fournisseur manquant pour crédit.
    """
    if lieu.type_lieu != Lieu.TYPE_MPSL:
        raise ErreurStock(f"Le lieu '{lieu}' n'est pas un dépôt MPSL.")
    if not produits:
        raise ErreurStock("Au moins un produit est requis.")
    if type_paiement not in ("cash", "credit", "partiel"):
        raise ErreurStock(f"type_paiement invalide : '{type_paiement}'.")
    if type_paiement in ("credit", "partiel") and fournisseur is None:
        raise ErreurStock("Un fournisseur est requis pour un achat à crédit ou partiel.")

    # Calculer le total général pour le JournalPayable unique
    prix_total_global = Decimal("0")
    for p in produits:
        q = Decimal(str(p["quantite"]))
        pu = Decimal(str(p.get("prix_unitaire") or "0"))
        prix_total_global += q * pu

    # Créer le JournalPayable unique (si crédit ou partiel)
    # montant_initial = TOTAL de la commande ; montant_paye = acompte versé.
    # montant_restant = montant_initial - montant_paye = dette fournisseur réelle.
    journal_shared = None
    if type_paiement in ("credit", "partiel") and fournisseur is not None and created_by is not None:
        from finance.models import JournalPayable
        if prix_total_global > Decimal("0"):
            noms = ", ".join(p["produit_nom"].strip() for p in produits[:3])
            if len(produits) > 3:
                noms += f" (+{len(produits) - 3})"
            journal_shared = JournalPayable.objects.create(
                creancier=fournisseur,
                reference=f"ACHAT-MPSL-BATCH-{lieu.pk}",
                description=f"Achat MPSL groupé : {noms}",
                montant_initial=prix_total_global,
                montant_paye=acompte if type_paiement == "partiel" else Decimal("0"),
                created_by=created_by,
            )

    achats = []
    for i, p in enumerate(produits):
        nom = (p["produit_nom"] or "").strip()
        if not nom:
            raise ErreurStock(f"Ligne {i + 1} : nom du produit obligatoire.")
        quantite = Decimal(str(p["quantite"]))
        unite = p.get("unite") or "sacs"
        prix_unitaire = Decimal(str(p.get("prix_unitaire") or "0"))
        notes = p.get("notes") or ""
        poids_par_sac = p.get("poids_par_sac")

        if quantite <= 0:
            raise ErreurStock(f"Ligne {i + 1} ({nom}) : quantité doit être > 0.")
        # poids_par_sac est facultatif ; conversions sac→kg indisponibles sans lui.

        prix_total_ligne = quantite * prix_unitaire
        existing = Produit.objects.filter(
            nom__iexact=nom,
            entreprise_id=lieu.entreprise_id,
        ).first()
        if not existing:
            unite_norm = _normaliser_unite_stock(unite)
            unite_produit = "sac" if unite_norm == "sac" else "kg"
            create_kwargs = dict(nom=nom, entreprise_id=lieu.entreprise_id, unite=unite_produit)
            if poids_par_sac is not None:
                create_kwargs["poids_par_sac"] = poids_par_sac
            existing = Produit.objects.create(**create_kwargs)
        elif poids_par_sac is not None and existing.poids_par_sac != poids_par_sac:
            existing.poids_par_sac = poids_par_sac
            existing.save(update_fields=["poids_par_sac"])

        achat = AchatMPSL.objects.create(
            lieu=lieu,
            fournisseur=fournisseur,
            produit_nom=nom,
            quantite=quantite,
            unite=unite,
            prix_unitaire=prix_unitaire,
            prix_total=prix_total_ligne,
            type_paiement=type_paiement,
            # L'acompte global est enregistré sur CHAQUE ligne pour traçabilité
            # (le JournalPayable unique en est la source de vérité).
            montant_paye_initial=acompte if type_paiement == "partiel" else Decimal("0"),
            journal_payable=journal_shared,
            notes=notes,
            created_by=created_by,
        )

        # Mise à jour stock — même pattern safe que enregistrer_achat_mpsl :
        # get_or_create sans verrou, puis select_for_update sur la ligne existante.
        u_stock = _normaliser_unite_stock(unite)
        stock, _ = Stock.objects.get_or_create(
            produit=existing,
            lieu=lieu,
            defaults={"quantite": Decimal("0")},
        )
        stock = Stock.objects.select_for_update().get(pk=stock.pk)
        if u_stock == "sac":
            stock.quantite += quantite
            stock.save(update_fields=["quantite", "updated_at"])
        elif u_stock in ("kg", "tonne"):
            qty_kg = _kg_depuis_unite(quantite, u_stock) if u_stock == "tonne" else quantite
            stock.quantite_kg += qty_kg
            stock.save(update_fields=["quantite_kg", "updated_at"])
        else:
            raise ErreurStock(f"Unité non supportée : '{unite}'.")

        achats.append(achat)

    return achats


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
            stock_from.save(update_fields=["quantite", "updated_at"])

            # Crédit stock destination (créer si absent)
            stock_to = Stock.objects.select_for_update().filter(produit=produit, lieu=to_lieu).first()
            if stock_to is None:
                Stock.objects.create(produit=produit, lieu=to_lieu, quantite=quantite)
            else:
                stock_to.quantite += quantite
                stock_to.save(update_fields=["quantite", "updated_at"])

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
    *,
    updated_by=None,
    log_request=None,
) -> Transfert:
    """
    Transfère des produits depuis un dépôt MPSL vers une usine ou un magasin.
    Le MPSL est la source d'approvisionnement : son stock est contrôlé.
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

    with transaction.atomic():
        normalized: list[tuple] = []
        for line in lignes:
            produit = line[0]
            quantite = Decimal(str(line[1]))
            unite = line[2] if len(line) > 2 else getattr(produit, "unite", "kg")
            if quantite <= 0:
                raise ErreurStock(f"Quantité invalide pour {produit} : {quantite}.")
            # ── Validation unité native du produit ────────────────────────────
            _valider_unite_transfert(produit, unite, from_mpsl)
            try:
                stock_src = Stock.objects.select_for_update().get(produit=produit, lieu=from_mpsl)
            except Stock.DoesNotExist:
                raise ErreurStock(f"Aucun stock pour '{produit}' à '{from_mpsl}'.")
            _verifier_stock_disponible(stock_src, quantite, unite)
            normalized.append((produit, quantite, unite))

        transfert = Transfert.objects.create(from_lieu=from_mpsl, to_lieu=to_lieu)

        for produit, quantite, unite in normalized:
            MouvementStock.objects.create(
                transfert=transfert,
                produit=produit,
                quantite=quantite,
                unit_price=Decimal("0"),
            )

            # Débit stock source
            _prelever_stock_unite(
                stock=Stock.objects.get(produit=produit, lieu=from_mpsl),
                quantite=quantite,
                unite=unite,
                updated_by=updated_by,
                log_request=log_request,
            )

            # Créditer la destination selon l'unité.
            # get_or_create sans lock, puis SELECT FOR UPDATE sur pk — pattern safe.
            stock_dest, _ = Stock.objects.get_or_create(
                produit=produit,
                lieu=to_lieu,
                defaults={"quantite": Decimal("0")},
            )
            stock_dest = Stock.objects.select_for_update().get(pk=stock_dest.pk)
            u_norm = _normaliser_unite_stock(unite)
            if u_norm == "sac":
                stock_dest.quantite += quantite
                stock_dest.save(update_fields=["quantite", "updated_at"])
            elif u_norm == "kg":
                stock_dest.quantite_kg += quantite
                stock_dest.save(update_fields=["quantite_kg", "updated_at"])
            elif u_norm == "tonne":
                stock_dest.quantite_kg += _kg_depuis_unite(quantite, u_norm)
                stock_dest.save(update_fields=["quantite_kg", "updated_at"])
            else:
                raise ErreurStock(f"Unité non supportée : '{unite}'.")

    return transfert


# ─── Transferts depuis boutique ───────────────────────────────────────────────

def transfert_depuis_boutique(
    from_boutique: Lieu,
    to_lieu: Lieu,
    lignes: list[tuple],
    *,
    updated_by=None,
    log_request=None,
) -> Transfert:
    """
    Transfère des produits depuis une boutique vers une autre boutique, une usine ou un MPSL.

    Mêmes garanties que transfert_depuis_mpsl :
      - Atomique, select_for_update, isolation cross-tenant.
      - Débit source via _prelever_stock_unite (gère sacs/kg/conversions auto).
      - Crédit destination dans le bon champ (quantite ou quantite_kg selon l'unité).
      - MouvementStock créé pour l'historique/traçabilité.

    lignes : liste de tuples (produit, quantite, unite)
    """
    if from_boutique.type_lieu != Lieu.TYPE_MAGASIN:
        raise ErreurStock(f"Le lieu source '{from_boutique}' n'est pas une boutique.")
    if to_lieu.type_lieu not in (Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE, Lieu.TYPE_MPSL):
        raise ErreurStock(
            f"La destination '{to_lieu}' doit être une boutique, une usine ou un MPSL."
        )
    if from_boutique.entreprise_id != to_lieu.entreprise_id:
        raise ErreurStock("Transfert inter-entreprises interdit.")
    if from_boutique.id == to_lieu.id:
        raise ErreurStock("Origine et destination doivent être différents.")

    with transaction.atomic():
        normalized: list[tuple] = []
        for line in lignes:
            produit = line[0]
            quantite = Decimal(str(line[1]))
            unite = line[2] if len(line) > 2 else getattr(produit, "unite", "kg")
            if quantite <= 0:
                raise ErreurStock(f"Quantité invalide pour '{produit}' : {quantite}.")
            _valider_unite_transfert(produit, unite, from_boutique)
            try:
                stock_src = Stock.objects.select_for_update().get(
                    produit=produit, lieu=from_boutique
                )
            except Stock.DoesNotExist:
                raise ErreurStock(f"Aucun stock pour '{produit}' à '{from_boutique}'.")
            _verifier_stock_disponible(stock_src, quantite, unite)
            normalized.append((produit, quantite, unite))

        transfert = Transfert.objects.create(from_lieu=from_boutique, to_lieu=to_lieu)

        for produit, quantite, unite in normalized:
            MouvementStock.objects.create(
                transfert=transfert,
                produit=produit,
                quantite=quantite,
                unit_price=Decimal("0"),
            )

            # Débit stock source
            _prelever_stock_unite(
                stock=Stock.objects.get(produit=produit, lieu=from_boutique),
                quantite=quantite,
                unite=unite,
                updated_by=updated_by,
                log_request=log_request,
            )

            # Crédit stock destination — même logique que transfert_depuis_mpsl
            stock_dest, _ = Stock.objects.get_or_create(
                produit=produit,
                lieu=to_lieu,
                defaults={"quantite": Decimal("0")},
            )
            stock_dest = Stock.objects.select_for_update().get(pk=stock_dest.pk)
            u_norm = _normaliser_unite_stock(unite)
            if u_norm == "sac":
                stock_dest.quantite += quantite
                stock_dest.save(update_fields=["quantite", "updated_at"])
            elif u_norm == "kg":
                stock_dest.quantite_kg += quantite
                stock_dest.save(update_fields=["quantite_kg", "updated_at"])
            elif u_norm == "tonne":
                stock_dest.quantite_kg += _kg_depuis_unite(quantite, u_norm)
                stock_dest.save(update_fields=["quantite_kg", "updated_at"])
            else:
                raise ErreurStock(f"Unité non supportée : '{unite}'.")

    return transfert


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


# ─── Conversion sacs → kg (boutique) ─────────────────────────────────────────

def convertir_sac_en_kg(
    stock: Stock,
    nombre_sacs: int,
    updated_by,
    *,
    poids_par_sac_override: Decimal | None = None,
    idempotency_key: str | None = None,
    log_request=None,
) -> Decimal:
    """
    Convertit nombre_sacs sacs en kg pour le stock.

    - Décrémente stock.quantite de nombre_sacs
    - Incrémente stock.quantite_kg de (nombre_sacs × poids_par_sac)
    - poids_par_sac utilisé : poids_par_sac_override si fourni, sinon produit.poids_par_sac
    - Retourne le nombre de kg générés
    - Lève ErreurStock si aucun poids disponible, si stock insuffisant ou si
      nombre_sacs <= 0.

    Atomique (select_for_update + transaction).
    """
    from audit.services import audit_log

    if nombre_sacs <= 0:
        raise ErreurStock("Le nombre de sacs à convertir doit être >= 1.")

    with transaction.atomic():
        locked = Stock.objects.select_for_update().get(pk=stock.pk)

        pps = poids_par_sac_override or locked.produit.poids_par_sac
        if not pps:
            raise ErreurStock(
                f"Le produit '{locked.produit.nom}' n'a pas de poids_par_sac défini. "
                "Veuillez saisir le poids par sac manuellement."
            )
        if Decimal(str(nombre_sacs)) > locked.quantite:
            raise ErreurStock(
                f"Stock insuffisant : {locked.quantite} sac(s) disponible(s), "
                f"demande {nombre_sacs}."
            )

        kg = Decimal(str(nombre_sacs)) * pps
        locked.quantite    -= Decimal(str(nombre_sacs))
        locked.quantite_kg += kg
        locked.save(update_fields=["quantite", "quantite_kg", "updated_at"])

        # audit dans la transaction : rollback si l'audit échoue (cohérence garantie)
        extra = {
            "lieu":           locked.lieu.nom,
            "produit":        locked.produit.nom,
            "sacs_convertis": nombre_sacs,
            "kg_generes":     str(kg),
            "poids_par_sac":  str(pps),
        }
        if idempotency_key:
            extra["idempotency_key"] = idempotency_key

        audit_log(
            user=updated_by,
            action="conversion_sac_en_kg",
            object_type="Stock",
            object_id=stock.pk,
            extra=extra,
            request=log_request,
        )

    return kg
