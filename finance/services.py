"""
Finance services KONIS — Logique métier centralisée.

Toutes les opérations financières passent par ces fonctions.
Aucune logique métier dans les vues ou les modèles.

Règles :
  - Toute écriture est atomique (transaction.atomic)
  - Un journal soldé est verrouillé → toute tentative d'écriture lève JournalSoldeError
  - Un paiement > montant_restant lève PaiementExcessifError
  - Le verrouillage (locked_at) est posé automatiquement lors du soldage
  - Toutes les opérations sont tracées via audit_log()
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from audit.services import audit_log
from core.models import CustomUser, Entreprise

from .models import (
    CaisseSupremeTransaction,
    ClientFinance,
    Creancier,
    DepenseProjet,
    DepotProjet,
    Emprunt,
    JournalCreance,
    JournalPayable,
    LigneCreance,
    PaiementCreance,
    PaiementPayable,
    Projet,
    RemboursementEmprunt,
)


# ─── Exceptions métier ────────────────────────────────────────────────────────

class ErreurFinance(Exception):
    """Exception de base pour toutes les erreurs métier finance."""


class JournalSoldeError(ErreurFinance):
    """Le journal est soldé et verrouillé — aucune écriture supplémentaire."""


class PaiementExcessifError(ErreurFinance):
    """Le montant du paiement dépasse le solde restant du journal."""


class EmpruntRembourseError(ErreurFinance):
    """L'emprunt est déjà intégralement remboursé."""


class SoldeInsuffisantError(ErreurFinance):
    """Le solde de la caisse est insuffisant pour ce retrait."""


# ─── Helpers internes ─────────────────────────────────────────────────────────

def _verifier_journal_ouvert(journal) -> None:
    """Lève JournalSoldeError si le journal est déjà soldé."""
    if journal.est_solde:
        raise JournalSoldeError(
            f"Ce journal est soldé le {journal.locked_at:%d/%m/%Y %H:%M} — aucune modification possible."
        )


def _verifier_paiement(montant_paiement: Decimal, montant_restant: Decimal) -> None:
    """Lève PaiementExcessifError si le paiement dépasse le restant dû."""
    if montant_paiement > montant_restant:
        raise PaiementExcessifError(
            f"Paiement de {montant_paiement} FCFA impossible : "
            f"solde restant = {montant_restant} FCFA."
        )


def _solder_journal(journal, now=None) -> None:
    """Pose le statut soldé + locked_at sur un journal (toute classe avec ces champs)."""
    if now is None:
        now = timezone.now()
    journal.statut = "solde"
    journal.locked_at = now
    journal.save(update_fields=["statut", "locked_at"])


# ═══════════════════════════════════════════════════════════════════════════════
# PAYABLES — Dettes envers créanciers
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def creer_journal_payable(
    *,
    creancier: Creancier,
    description: str,
    montant_initial: Decimal,
    created_by: CustomUser,
    reference: str = "",
    date_echeance=None,
    notes: str = "",
) -> JournalPayable:
    """
    Crée un nouveau journal de dette envers un créancier.
    Chaque dette distincte doit avoir son propre journal.
    """
    journal = JournalPayable.objects.create(
        creancier=creancier,
        description=description,
        montant_initial=montant_initial,
        montant_paye=Decimal("0"),
        reference=reference,
        date_echeance=date_echeance,
        notes=notes,
        created_by=created_by,
    )
    audit_log(
        user=created_by,
        action="journal_payable_créé",
        object_type="JournalPayable",
        object_id=journal.pk,
        extra={
            "creancier": creancier.nom,
            "montant": str(montant_initial),
            "reference": reference,
        },
    )
    return journal


@transaction.atomic
def enregistrer_paiement_payable(
    *,
    journal: JournalPayable,
    montant: Decimal,
    date,
    created_by: CustomUser,
    mode_paiement: str = "especes",
    reference: str = "",
    notes: str = "",
) -> PaiementPayable:
    """
    Enregistre un paiement sur un journal payable.
    - Lève JournalSoldeError si le journal est déjà soldé.
    - Lève PaiementExcessifError si le montant dépasse le restant.
    - Solde et verrouille automatiquement le journal si le paiement est total.
    """
    # Recharger depuis la DB avec SELECT FOR UPDATE pour éviter les race conditions
    journal = JournalPayable.objects.select_for_update().get(pk=journal.pk)

    _verifier_journal_ouvert(journal)
    _verifier_paiement(montant, journal.montant_restant)

    paiement = PaiementPayable.objects.create(
        journal=journal,
        montant=montant,
        date=date,
        mode_paiement=mode_paiement,
        reference=reference,
        notes=notes,
        created_by=created_by,
    )

    journal.montant_paye += montant
    journal.save(update_fields=["montant_paye"])

    # Soldage automatique si entièrement payé
    auto_solde = journal.montant_paye >= journal.montant_initial
    if auto_solde:
        _solder_journal(journal)

    audit_log(
        user=created_by,
        action="paiement_payable_enregistré",
        object_type="PaiementPayable",
        object_id=paiement.pk,
        extra={
            "journal_id": journal.pk,
            "creancier": journal.creancier.nom,
            "montant": str(montant),
            "montant_restant": str(journal.montant_restant),
            "auto_solde": auto_solde,
        },
    )
    return paiement


@transaction.atomic
def solder_journal_payable(*, journal: JournalPayable, created_by: CustomUser) -> JournalPayable:
    """
    Solde manuellement un journal payable (même si montant_paye < montant_initial).
    Usage : abandon de dette, remise commerciale.
    """
    journal = JournalPayable.objects.select_for_update().get(pk=journal.pk)
    _verifier_journal_ouvert(journal)
    _solder_journal(journal)

    audit_log(
        user=created_by,
        action="journal_payable_soldé_manuellement",
        object_type="JournalPayable",
        object_id=journal.pk,
        extra={
            "creancier": journal.creancier.nom,
            "montant_initial": str(journal.montant_initial),
            "montant_paye": str(journal.montant_paye),
            "ecart": str(journal.montant_initial - journal.montant_paye),
        },
    )
    return journal


# ═══════════════════════════════════════════════════════════════════════════════
# CRÉANCES — Dettes de clients envers l'entreprise
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def creer_journal_creance(
    *,
    client: ClientFinance,
    description: str,
    montant_initial: Decimal,
    created_by: CustomUser,
    lignes: list | None = None,
    reference: str = "",
    date_echeance=None,
    notes: str = "",
) -> JournalCreance:
    """
    Crée un journal de créance client.
    Si `lignes` est fourni, crée aussi les LigneCreance.
    Format lignes : [{"description": str, "quantite": Decimal, "prix_unitaire": Decimal, "produit_id": int|None}]
    """
    journal = JournalCreance.objects.create(
        client=client,
        description=description,
        montant_initial=montant_initial,
        montant_paye=Decimal("0"),
        reference=reference,
        date_echeance=date_echeance,
        notes=notes,
        created_by=created_by,
    )

    if lignes:
        LigneCreance.objects.bulk_create([
            LigneCreance(
                journal=journal,
                description=l["description"],
                quantite=Decimal(str(l.get("quantite", "1"))),
                prix_unitaire=Decimal(str(l.get("prix_unitaire", "0"))),
                produit_id=l.get("produit_id"),
            )
            for l in lignes
        ])

    audit_log(
        user=created_by,
        action="journal_creance_créé",
        object_type="JournalCreance",
        object_id=journal.pk,
        extra={
            "client": client.nom,
            "montant": str(montant_initial),
            "nb_lignes": len(lignes) if lignes else 0,
        },
    )
    return journal


@transaction.atomic
def enregistrer_paiement_creance(
    *,
    journal: JournalCreance,
    montant: Decimal,
    date,
    created_by: CustomUser,
    mode_paiement: str = "especes",
    reference: str = "",
    notes: str = "",
) -> PaiementCreance:
    """
    Enregistre un paiement reçu d'un client sur un journal de créance.
    Solde et verrouille automatiquement si le paiement est total.
    """
    journal = JournalCreance.objects.select_for_update().get(pk=journal.pk)

    _verifier_journal_ouvert(journal)
    _verifier_paiement(montant, journal.montant_restant)

    paiement = PaiementCreance.objects.create(
        journal=journal,
        montant=montant,
        date=date,
        mode_paiement=mode_paiement,
        reference=reference,
        notes=notes,
        created_by=created_by,
    )

    journal.montant_paye += montant
    journal.save(update_fields=["montant_paye"])

    auto_solde = journal.montant_paye >= journal.montant_initial
    if auto_solde:
        _solder_journal(journal)

    audit_log(
        user=created_by,
        action="paiement_creance_enregistré",
        object_type="PaiementCreance",
        object_id=paiement.pk,
        extra={
            "journal_id": journal.pk,
            "client": journal.client.nom,
            "montant": str(montant),
            "montant_restant": str(journal.montant_restant),
            "auto_solde": auto_solde,
        },
    )
    return paiement


@transaction.atomic
def solder_journal_creance(*, journal: JournalCreance, created_by: CustomUser) -> JournalCreance:
    """Solde manuellement un journal de créance (remise, abandon de créance)."""
    journal = JournalCreance.objects.select_for_update().get(pk=journal.pk)
    _verifier_journal_ouvert(journal)
    _solder_journal(journal)

    audit_log(
        user=created_by,
        action="journal_creance_soldé_manuellement",
        object_type="JournalCreance",
        object_id=journal.pk,
        extra={
            "client": journal.client.nom,
            "montant_initial": str(journal.montant_initial),
            "montant_paye": str(journal.montant_paye),
        },
    )
    return journal


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRUNTS — Prêts bancaires
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def creer_emprunt(
    *,
    entreprise: Entreprise,
    nom: str,
    banque: str,
    montant_initial: Decimal,
    date_debut,
    created_by: CustomUser,
    taux_interet: Decimal | None = None,
    date_echeance=None,
    notes: str = "",
) -> Emprunt:
    """Enregistre un nouvel emprunt bancaire reçu."""
    emprunt = Emprunt.objects.create(
        entreprise=entreprise,
        nom=nom,
        banque=banque,
        montant_initial=montant_initial,
        montant_rembourse=Decimal("0"),
        taux_interet=taux_interet,
        date_debut=date_debut,
        date_echeance=date_echeance,
        notes=notes,
        created_by=created_by,
    )
    audit_log(
        user=created_by,
        action="emprunt_créé",
        object_type="Emprunt",
        object_id=emprunt.pk,
        extra={"banque": banque, "montant": str(montant_initial)},
    )
    return emprunt


@transaction.atomic
def enregistrer_remboursement(
    *,
    emprunt: Emprunt,
    montant: Decimal,
    date,
    created_by: CustomUser,
    reference: str = "",
    notes: str = "",
) -> RemboursementEmprunt:
    """
    Enregistre un remboursement d'emprunt.
    - Lève EmpruntRembourseError si l'emprunt est déjà soldé.
    - Lève PaiementExcessifError si le montant dépasse le restant.
    - Solde automatiquement l'emprunt si entièrement remboursé.
    """
    emprunt = Emprunt.objects.select_for_update().get(pk=emprunt.pk)

    if emprunt.est_rembourse:
        raise EmpruntRembourseError(
            f"L'emprunt '{emprunt.nom}' est déjà intégralement remboursé."
        )
    _verifier_paiement(montant, emprunt.montant_restant)

    remboursement = RemboursementEmprunt.objects.create(
        emprunt=emprunt,
        montant=montant,
        date=date,
        reference=reference,
        notes=notes,
        created_by=created_by,
    )

    emprunt.montant_rembourse += montant
    emprunt.save(update_fields=["montant_rembourse"])

    auto_solde = emprunt.montant_rembourse >= emprunt.montant_initial
    if auto_solde:
        now = timezone.now()
        emprunt.statut = "rembourse"
        emprunt.locked_at = now
        emprunt.save(update_fields=["statut", "locked_at"])

    audit_log(
        user=created_by,
        action="remboursement_emprunt_enregistré",
        object_type="RemboursementEmprunt",
        object_id=remboursement.pk,
        extra={
            "emprunt_id": emprunt.pk,
            "banque": emprunt.banque,
            "montant": str(montant),
            "montant_restant": str(emprunt.montant_restant),
            "auto_solde": auto_solde,
        },
    )
    return remboursement


# ═══════════════════════════════════════════════════════════════════════════════
# CAISSE SUPRÊME — Trésorerie centrale
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def enregistrer_transaction_caisse(
    *,
    entreprise: Entreprise,
    type_transaction: str,
    montant: Decimal,
    description: str,
    date,
    created_by: CustomUser,
    reference: str = "",
    verifier_solde: bool = True,
) -> CaisseSupremeTransaction:
    """
    Enregistre un mouvement de la caisse centrale.
    - type_transaction : 'depot' ou 'retrait'
    - verifier_solde : si True, lève SoldeInsuffisantError si retrait > solde disponible
    """
    if type_transaction == "retrait" and verifier_solde:
        # Verrouiller la ligne entreprise pour sérialiser les retraits concurrents
        # et éviter la race condition (double retrait simultané → découvert).
        Entreprise.objects.select_for_update().get(pk=entreprise.pk)
        solde_actuel = get_solde_caisse(entreprise)
        if montant > solde_actuel:
            raise SoldeInsuffisantError(
                f"Retrait de {montant} FCFA impossible : solde caisse = {solde_actuel} FCFA."
            )

    transaction_caisse = CaisseSupremeTransaction.objects.create(
        entreprise=entreprise,
        type_transaction=type_transaction,
        montant=montant,
        description=description,
        reference=reference,
        date=date,
        created_by=created_by,
    )
    audit_log(
        user=created_by,
        action=f"caisse_{type_transaction}",
        object_type="CaisseSupremeTransaction",
        object_id=transaction_caisse.pk,
        extra={"montant": str(montant), "description": description},
    )
    return transaction_caisse


def get_solde_caisse(entreprise: Entreprise) -> Decimal:
    """
    Calcule le solde courant de la caisse centrale.
    Solde = Σ dépôts − Σ retraits
    """
    from django.db.models import Sum, Q
    qs = CaisseSupremeTransaction.objects.filter(entreprise=entreprise)
    result = qs.aggregate(
        total_depots=Sum("montant", filter=Q(type_transaction="depot")),
        total_retraits=Sum("montant", filter=Q(type_transaction="retrait")),
    )
    depots   = result["total_depots"]   or Decimal("0")
    retraits = result["total_retraits"] or Decimal("0")
    return depots - retraits


# ═══════════════════════════════════════════════════════════════════════════════
# PROJETS — Budget et suivi
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def creer_projet(
    *,
    entreprise: Entreprise,
    nom: str,
    budget_initial: Decimal,
    date_debut,
    created_by: CustomUser,
    description: str = "",
    date_fin=None,
) -> Projet:
    """Crée un nouveau projet avec son budget initial."""
    projet = Projet.objects.create(
        entreprise=entreprise,
        nom=nom,
        description=description,
        budget_initial=budget_initial,
        date_debut=date_debut,
        date_fin=date_fin,
        created_by=created_by,
    )
    audit_log(
        user=created_by,
        action="projet_créé",
        object_type="Projet",
        object_id=projet.pk,
        extra={"nom": nom, "budget": str(budget_initial)},
    )
    return projet


@transaction.atomic
def enregistrer_depense_projet(
    *,
    projet: Projet,
    montant: Decimal,
    description: str,
    date,
    created_by: CustomUser,
) -> DepenseProjet:
    """Enregistre une dépense sur un projet (pas de plafond bloquant — alerte si dépassement)."""
    depense = DepenseProjet.objects.create(
        projet=projet,
        montant=montant,
        description=description,
        date=date,
        created_by=created_by,
    )
    # Calculer le budget restant après cette dépense (informatif, non bloquant)
    restant = get_budget_restant_projet(projet)
    audit_log(
        user=created_by,
        action="depense_projet_enregistrée",
        object_type="DepenseProjet",
        object_id=depense.pk,
        extra={
            "projet_id": projet.pk,
            "projet_nom": projet.nom,
            "montant": str(montant),
            "budget_restant": str(restant),
            "depassement": restant < Decimal("0"),
        },
    )
    return depense


@transaction.atomic
def enregistrer_depot_projet(
    *,
    projet: Projet,
    montant: Decimal,
    description: str,
    date,
    created_by: CustomUser,
) -> DepotProjet:
    """Enregistre des fonds supplémentaires reçus pour un projet."""
    depot = DepotProjet.objects.create(
        projet=projet,
        montant=montant,
        description=description,
        date=date,
        created_by=created_by,
    )
    audit_log(
        user=created_by,
        action="depot_projet_enregistré",
        object_type="DepotProjet",
        object_id=depot.pk,
        extra={"projet_id": projet.pk, "montant": str(montant)},
    )
    return depot


def get_budget_restant_projet(projet: Projet) -> Decimal:
    """
    Calcule le budget restant d'un projet.
    Budget restant = budget_initial + Σ dépôts − Σ dépenses
    Une valeur négative indique un dépassement budgétaire.
    """
    from django.db.models import Sum
    depots   = projet.depots.aggregate(total=Sum("montant"))["total"]   or Decimal("0")
    depenses = projet.depenses.aggregate(total=Sum("montant"))["total"] or Decimal("0")
    return projet.budget_initial + depots - depenses


# ═══════════════════════════════════════════════════════════════════════════════
# TABLEAU DE BORD — Agrégats financiers globaux
# ═══════════════════════════════════════════════════════════════════════════════

def get_resume_financier(entreprise: Entreprise) -> dict:
    """
    Retourne un résumé financier global pour le dashboard supreme_admin / DAF.

    Champs retournés :
      - total_creances_restantes  : Σ montant_restant des créances en_cours
      - total_payables_restants   : Σ montant_restant des dettes en_cours
      - total_emprunts_restants   : Σ montant_restant des emprunts en_cours
      - solde_caisse              : solde courant de la caisse suprême
      - projets_en_cours          : nombre de projets actifs
      - projets_en_depassement    : nombre de projets avec budget_restant < 0
    """
    from django.db.models import Sum, Count, Q, F, ExpressionWrapper, DecimalField

    # Créances en cours
    creances = JournalCreance.objects.filter(
        client__entreprise=entreprise,
        statut="en_cours",
    ).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("montant_initial") - F("montant_paye"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )

    # Payables en cours
    payables = JournalPayable.objects.filter(
        creancier__entreprise=entreprise,
        statut="en_cours",
    ).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("montant_initial") - F("montant_paye"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )

    # Emprunts en cours
    emprunts = Emprunt.objects.filter(
        entreprise=entreprise,
        statut="en_cours",
    ).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("montant_initial") - F("montant_rembourse"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
    )

    # Projets
    projets_qs = Projet.objects.filter(entreprise=entreprise, statut="en_cours")
    nb_projets = projets_qs.count()
    nb_depassement = sum(
        1 for p in projets_qs
        if get_budget_restant_projet(p) < Decimal("0")
    )

    return {
        "total_creances_restantes": creances["total"] or Decimal("0"),
        "total_payables_restants":  payables["total"] or Decimal("0"),
        "total_emprunts_restants":  emprunts["total"] or Decimal("0"),
        "solde_caisse":             get_solde_caisse(entreprise),
        "projets_en_cours":         nb_projets,
        "projets_en_depassement":   nb_depassement,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# COLLECTE ARGENT — Passage du collectionneur
# ═══════════════════════════════════════════════════════════════════════════════

@transaction.atomic
def enregistrer_collecte(
    *,
    lieu,
    date_collecte,
    montant_trouve: Decimal,
    montant_pris: Decimal,
    collecteur=None,
    notes: str = "",
    created_by: CustomUser,
    deposer_en_banque: bool = False,
    entreprise: Entreprise | None = None,
):
    """
    Enregistre le passage du collectionneur dans une boutique.

    montant_laisse = montant_trouve - montant_pris  (calculé automatiquement).

    Si deposer_en_banque=True ET entreprise fourni :
      → crée une CaisseSupremeTransaction (dépôt banque) liée à cette collecte.

    Lève ValueError si montant_pris > montant_trouve.
    """
    from finance.models import CollecteArgent

    if montant_pris > montant_trouve:
        raise ErreurFinance(
            f"montant_pris ({montant_pris}) ne peut dépasser montant_trouve ({montant_trouve})."
        )
    if montant_trouve < Decimal("0"):
        raise ErreurFinance("montant_trouve doit être >= 0.")

    collecte = CollecteArgent.objects.create(
        lieu=lieu,
        collecteur=collecteur,
        date_collecte=date_collecte,
        montant_trouve=montant_trouve,
        montant_pris=montant_pris,
        montant_laisse=montant_trouve - montant_pris,
        notes=notes or "",
        created_by=created_by,
    )

    if deposer_en_banque and montant_pris > Decimal("0") and entreprise is not None:
        tx = enregistrer_transaction_caisse(
            entreprise=entreprise,
            type_transaction="depot",
            montant=montant_pris,
            description=f"Dépôt collecte — {lieu.nom} ({date_collecte})",
            date=date_collecte,
            created_by=created_by,
            reference=f"COLLECTE-{collecte.pk}",
        )
        collecte.depot_banque = tx
        collecte.save(update_fields=["depot_banque"])

    audit_log(
        user=created_by,
        action="collecte_enregistrée",
        object_type="CollecteArgent",
        object_id=collecte.pk,
        extra={
            "lieu": lieu.nom,
            "date": str(date_collecte),
            "montant_trouve": str(montant_trouve),
            "montant_pris": str(montant_pris),
            "montant_laisse": str(collecte.montant_laisse),
            "depot_banque": deposer_en_banque,
        },
    )
    return collecte


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD — Agrégats globaux étendus (ventes + cash + créances + dettes + dépenses)
# ═══════════════════════════════════════════════════════════════════════════════

def get_dashboard_global(entreprise: Entreprise) -> dict:
    """
    Dashboard global admin/DAF.

    Retourne :
      total_ventes          : Σ montant_total de tous les tickets (toutes boutiques)
      total_cash            : Σ montant_cash des tickets (argent réellement encaissé)
      total_credit          : Σ montant_credit des tickets (créances)
      total_creances        : Σ montant_restant des JournalCreance en_cours
      total_dettes_fourn    : Σ montant_restant des JournalPayable en_cours
      total_depenses        : Σ montant des Depense (toutes boutiques, entreprise)
      solde_caisse          : solde CaisseSupremeTransaction
      argent_theorique      : total_cash + total_credit (= total_ventes)
      benefice_brut         : total_ventes - total_achats_mpsl
      benefice_net          : benefice_brut - total_depenses
    """
    from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Q
    from ventes.models import Ticket
    from inventaire.models import AchatMPSL
    from depenses.models import Depense

    # Ventes
    tickets = Ticket.objects.filter(lieu__entreprise=entreprise).aggregate(
        total_ventes=Sum("montant_total"),
        total_cash=Sum("montant_cash"),
        total_credit_ventes=Sum("montant_credit"),
    )

    # Créances restantes
    creances = JournalCreance.objects.filter(
        client__entreprise=entreprise, statut="en_cours"
    ).aggregate(
        total=Sum(ExpressionWrapper(
            F("montant_initial") - F("montant_paye"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )

    # Dettes fournisseurs restantes
    dettes = JournalPayable.objects.filter(
        creancier__entreprise=entreprise, statut="en_cours"
    ).aggregate(
        total=Sum(ExpressionWrapper(
            F("montant_initial") - F("montant_paye"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )

    # Achats MPSL (coût d'achat fournisseurs)
    achats = AchatMPSL.objects.filter(lieu__entreprise=entreprise).aggregate(
        total=Sum("prix_total")
    )

    # Dépenses
    depenses = Depense.objects.filter(entreprise=entreprise).aggregate(
        total=Sum("montant")
    )

    tv       = tickets["total_ventes"]        or Decimal("0")
    tc       = tickets["total_cash"]          or Decimal("0")
    tcr      = tickets["total_credit_ventes"] or Decimal("0")
    creances_restantes = creances["total"]    or Decimal("0")
    dettes_restantes   = dettes["total"]      or Decimal("0")
    total_achats       = achats["total"]      or Decimal("0")
    total_dep          = depenses["total"]    or Decimal("0")
    solde              = get_solde_caisse(entreprise)
    ben_brut           = tv - total_achats
    ben_net            = ben_brut - total_dep

    return {
        "total_ventes":       tv,
        "total_cash":         tc,
        "total_credit":       tcr,
        "total_creances":     creances_restantes,
        "total_dettes_fourn": dettes_restantes,
        "total_depenses":     total_dep,
        "solde_caisse":       solde,
        "argent_theorique":   tc + creances_restantes,
        "benefice_brut":      ben_brut,
        "benefice_net":       ben_net,
    }


def get_dashboard_boutique(lieu) -> dict:
    """
    Dashboard par boutique (rôle boutique, admin).

    Retourne : ventes, cash, créances, dépenses, stock_valeur, nb_produits_stock
    """
    from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField, Q
    from ventes.models import Ticket
    from depenses.models import Depense
    from inventaire.models import Stock

    tickets = Ticket.objects.filter(lieu=lieu).aggregate(
        total_ventes=Sum("montant_total"),
        total_cash=Sum("montant_cash"),
        total_credit=Sum("montant_credit"),
    )
    creances = JournalCreance.objects.filter(lieu=lieu, statut="en_cours").aggregate(
        total=Sum(ExpressionWrapper(
            F("montant_initial") - F("montant_paye"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )
    depenses = Depense.objects.filter(lieu=lieu).aggregate(total=Sum("montant"))
    stock_nb = Stock.objects.filter(lieu=lieu, quantite__gt=0).count()

    return {
        "total_ventes":   tickets["total_ventes"]  or Decimal("0"),
        "total_cash":     tickets["total_cash"]    or Decimal("0"),
        "total_credit":   tickets["total_credit"]  or Decimal("0"),
        "total_creances": creances["total"]         or Decimal("0"),
        "total_depenses": depenses["total"]         or Decimal("0"),
        "nb_produits_en_stock": stock_nb,
    }
