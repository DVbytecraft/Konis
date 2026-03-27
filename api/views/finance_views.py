"""
API Finance KONIS — Payables, Créances, Emprunts, Caisse Suprême, Projets.

Accès : IsDafRole (supreme_admin + admin + daf).
Toute la logique métier est déléguée à finance/services.py.
"""
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, CreateModelMixin, UpdateModelMixin

from api.idempotency import IdempotencyGuard
from api.throttling import FinanceCreateRateThrottle
from api.permissions import IsDafRole, IsAdminRole, DafReadOnlyMixin, IsCollecteurRole, IsComptableRole
from api.serializers_finance import (
    CaisseTransactionCreateSerializer,
    CaisseTransactionSerializer,
    ClientFinanceCreateSerializer,
    ClientFinanceSerializer,
    CollecteArgentCreateSerializer,
    CollecteArgentSerializer,
    CollecteArgentUpdateSerializer,
    CreancierCreateSerializer,
    CreancierSerializer,
    DashboardGlobalSerializer,
    DepenseProjetCreateSerializer,
    DepotProjetCreateSerializer,
    EmpruntCreateSerializer,
    EmpruntSerializer,
    JournalCreanceCreateSerializer,
    JournalCreanceSerializer,
    JournalPayableCreateSerializer,
    JournalPayableSerializer,
    PaiementCreanceCreateSerializer,
    PaiementPayableCreateSerializer,
    ProjetCreateSerializer,
    ProjetSerializer,
    RemboursementCreateSerializer,
    ResumeFinancierSerializer,
)
from core.models import Lieu
from finance.models import (
    CaisseSupremeTransaction,
    ClientFinance,
    CollecteArgent,
    Creancier,
    Emprunt,
    JournalCreance,
    JournalPayable,
    Projet,
)
from finance.services import (
    ErreurFinance,
    creer_emprunt,
    creer_journal_creance,
    creer_journal_payable,
    creer_projet,
    enregistrer_collecte,
    enregistrer_depot_projet,
    enregistrer_depense_projet,
    enregistrer_paiement_creance,
    enregistrer_paiement_payable,
    enregistrer_remboursement,
    enregistrer_transaction_caisse,
    get_caisse_physique_boutique,
    get_dashboard_global,
    get_resume_financier,
    get_solde_caisse,
    solder_journal_creance,
    solder_journal_payable,
)


def _get_entreprise(request):
    return request.user.entreprise


def _err(exc: ErreurFinance):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

class FinanceResumeView(APIView):
    """GET /api/finance/resume/ — Résumé financier global (supreme_admin / DAF)."""
    permission_classes = [IsDafRole]

    def get(self, request):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)
        resume = get_resume_financier(_get_entreprise(request))
        ser = ResumeFinancierSerializer(resume)
        return Response(ser.data)


# ═══════════════════════════════════════════════════════════════════════════════
# CRÉANCIERS
# ═══════════════════════════════════════════════════════════════════════════════

class CreancierViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    """
    GET    /api/finance/creanciers/       — liste
    POST   /api/finance/creanciers/       — créer  (admin, DAF, COMPTABLE)
    GET    /api/finance/creanciers/{id}/  — détail
    PATCH  /api/finance/creanciers/{id}/  — modifier nom/contact/notes (admin, DAF uniquement)
    """
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]
    # Le COMPTABLE peut créer des créanciers (fournisseurs/partenaires financiers).
    # Le DAF reste en lecture seule — modifier/destroy lui sont toujours bloqués.
    _COMPTABLE_ALLOWED_WRITE_ACTIONS = frozenset({"create"})

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return Creancier.objects.none()
        return Creancier.objects.filter(entreprise_id=ent_id).order_by("nom")

    def get_serializer_class(self):
        if self.action == "create":
            return CreancierCreateSerializer
        return CreancierSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)
        ser = CreancierCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = Creancier.objects.create(
            entreprise=_get_entreprise(request),
            **ser.validated_data,
        )
        return Response(CreancierSerializer(obj).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"])
    def modifier(self, request, pk=None):
        obj = self.get_object()
        ser = CreancierCreateSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        for attr, val in ser.validated_data.items():
            setattr(obj, attr, val)
        obj.save()
        return Response(CreancierSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """
        POST /api/finance/creanciers/{id}/activate/
        Active un fournisseur en attente (statut pending -> actif).
        Réservé aux admins/DAF/comptable uniquement.
        """
        from core.models import CustomUser as CU
        ROLES_AUTORISES = {CU.ROLE_SUPREME_ADMIN, CU.ROLE_ADMIN, CU.ROLE_DAF, CU.ROLE_COMPTABLE}
        if request.user.role not in ROLES_AUTORISES:
            return Response(
                {"detail": "Seul admin, DAF ou comptable peut activer un fournisseur."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        creancier = self.get_object()
        if creancier.statut == "actif":
            return Response(
                {"detail": f"Le fournisseur '{creancier.nom}' est déjà actif."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        creancier.statut = "actif"
        creancier.save(update_fields=["statut", "updated_at"])
        
        from audit.services import audit_log
        audit_log(
            user=request.user,
            action="creancier_activé",
            object_type="Creancier",
            object_id=creancier.pk,
            extra={"creancier": creancier.nom},
        )
        
        return Response(CreancierSerializer(creancier).data)

    @action(detail=True, methods=["post"])
    def desactivate(self, request, pk=None):
        """
        POST /api/finance/creanciers/{id}/desactivate/
        Désactive un fournisseur (statut actif -> inactif).
        Un fournisseur inactif ne peut plus être utilisé.
        Réservé aux admins/DAF/comptable uniquement.
        """
        from core.models import CustomUser as CU
        ROLES_AUTORISES = {CU.ROLE_SUPREME_ADMIN, CU.ROLE_ADMIN, CU.ROLE_DAF, CU.ROLE_COMPTABLE}
        if request.user.role not in ROLES_AUTORISES:
            return Response(
                {"detail": "Seul admin, DAF ou comptable peut désactiver un fournisseur."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        creancier = self.get_object()
        if creancier.statut == "inactif":
            return Response(
                {"detail": f"Le fournisseur '{creancier.nom}' est déjà inactif."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ancien_statut = creancier.statut
        creancier.statut = "inactif"
        creancier.save(update_fields=["statut", "updated_at"])
        
        from audit.services import audit_log
        audit_log(
            user=request.user,
            action="creancier_désactivé",
            object_type="Creancier",
            object_id=creancier.pk,
            extra={"creancier": creancier.nom, "statut_avant": ancien_statut},
        )
        
        return Response(CreancierSerializer(creancier).data)


# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAUX PAYABLES
# ═══════════════════════════════════════════════════════════════════════════════

class JournalPayableViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    """
    GET  /api/finance/journaux-payables/             — liste
    POST /api/finance/journaux-payables/             — créer journal
    GET  /api/finance/journaux-payables/{id}/        — détail + paiements
    POST /api/finance/journaux-payables/{id}/paiement/ — enregistrer paiement
    POST /api/finance/journaux-payables/{id}/solder/   — solder manuellement
    """
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return JournalPayable.objects.none()
        qs = JournalPayable.objects.filter(
            creancier__entreprise_id=ent_id,
        ).select_related("creancier").prefetch_related("paiements")

        statut = self.request.query_params.get("statut")
        if statut in ("en_cours", "solde"):
            qs = qs.filter(statut=statut)

        creancier_id = self.request.query_params.get("creancier_id")
        if creancier_id:
            qs = qs.filter(creancier_id=creancier_id)

        return qs.order_by("-created_at")

    def get_serializer_class(self):
        return JournalPayableSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)

        guard = IdempotencyGuard(request, "creer_journal_payable")
        early = guard.check(success_status=status.HTTP_201_CREATED)
        if early is not None:
            return early

        ser = JournalPayableCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        # SÉCURITÉ : Validation à deux niveaux pour montants élevés
        MONTANT_ELEVE = Decimal("1000000")  # 1 million
        if d["montant_initial"] >= MONTANT_ELEVE:
            if not request.data.get("code_validation"):
                return Response(
                    {"detail": "Montant élevé. Un code de validation est requis.", "code_validation_required": True},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Ici on vérifierait le code (à implémenter selon votre système)
            # Pour l'instant, on accepte si le code est présent

        try:
            creancier = Creancier.objects.get(
                pk=d["creancier_id"],
                entreprise_id=request.user.entreprise_id,
            )
        except Creancier.DoesNotExist:
            return Response({"detail": "Créancier introuvable."}, status=status.HTTP_404_NOT_FOUND)
        
        # SÉCURITÉ : Le créancier doit être actif pour être utilisé
        if creancier.statut != "actif":
            return Response(
                {"detail": f"Créancier '{creancier.nom}' en attente de validation. Contacter admin pour activation."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            journal = creer_journal_payable(
                creancier=creancier,
                description=d["description"],
                montant_initial=d["montant_initial"],
                created_by=request.user,
                reference=d.get("reference", ""),
                date_echeance=d.get("date_echeance"),
                notes=d.get("notes", ""),
            )
        except ErreurFinance as e:
            return _err(e)

        resp_data = JournalPayableSerializer(journal).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def paiement(self, request, pk=None):
        journal = self.get_object()
        guard = IdempotencyGuard(request, "paiement_payable")
        early = guard.check()
        if early is not None:
            return early

        ser = PaiementPayableCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            enregistrer_paiement_payable(
                journal=journal,
                montant=d["montant"],
                date=d["date"],
                created_by=request.user,
                mode_paiement=d.get("mode_paiement", "especes"),
                reference=d.get("reference", ""),
                notes=d.get("notes", ""),
            )
        except ErreurFinance as e:
            return _err(e)
        journal.refresh_from_db()
        resp_data = JournalPayableSerializer(journal).data
        guard.success(resp_data)
        return Response(resp_data)

    @action(detail=True, methods=["post"])
    def solder(self, request, pk=None):
        journal = self.get_object()
        try:
            solder_journal_payable(journal=journal, created_by=request.user)
        except ErreurFinance as e:
            return _err(e)
        journal.refresh_from_db()
        return Response(JournalPayableSerializer(journal).data)


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTS FINANCE
# ═══════════════════════════════════════════════════════════════════════════════

class ClientFinanceViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return ClientFinance.objects.none()
        return ClientFinance.objects.filter(entreprise_id=ent_id).order_by("nom")

    def get_serializer_class(self):
        if self.action == "create":
            return ClientFinanceCreateSerializer
        return ClientFinanceSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)
        ser = ClientFinanceCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        # C2 : valider que le lieu appartient à la même entreprise que l'utilisateur
        lieu = d.get("lieu")
        if lieu is not None and lieu.entreprise_id != request.user.entreprise_id:
            return Response(
                {"detail": "Lieu invalide ou non autorisé pour cette entreprise."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj = ClientFinance.objects.create(entreprise=_get_entreprise(request), **d)
        return Response(ClientFinanceSerializer(obj).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"])
    def modifier(self, request, pk=None):
        obj = self.get_object()
        ser = ClientFinanceCreateSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        # C2 : valider le lieu si fourni dans le patch
        lieu = d.get("lieu")
        if lieu is not None and lieu.entreprise_id != request.user.entreprise_id:
            return Response(
                {"detail": "Lieu invalide ou non autorisé pour cette entreprise."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for attr, val in d.items():
            setattr(obj, attr, val)
        obj.save()
        return Response(ClientFinanceSerializer(obj).data)


# ═══════════════════════════════════════════════════════════════════════════════
# JOURNAUX CRÉANCES
# ═══════════════════════════════════════════════════════════════════════════════

class JournalCreanceViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    """
    GET  /api/finance/journaux-creances/               — liste
    POST /api/finance/journaux-creances/               — créer
    GET  /api/finance/journaux-creances/{id}/          — détail + lignes + paiements
    POST /api/finance/journaux-creances/{id}/paiement/ — enregistrer paiement reçu
    POST /api/finance/journaux-creances/{id}/solder/   — solder manuellement
    """
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return JournalCreance.objects.none()
        qs = JournalCreance.objects.filter(
            client__entreprise_id=ent_id,
        ).select_related("client").prefetch_related("lignes__produit", "paiements")

        statut = self.request.query_params.get("statut")
        if statut in ("en_cours", "solde"):
            qs = qs.filter(statut=statut)

        client_id = self.request.query_params.get("client_id")
        if client_id:
            qs = qs.filter(client_id=client_id)

        return qs.order_by("-created_at")

    def get_serializer_class(self):
        return JournalCreanceSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)

        guard = IdempotencyGuard(request, "creer_journal_creance")
        early = guard.check(success_status=status.HTTP_201_CREATED)
        if early is not None:
            return early

        ser = JournalCreanceCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            client = ClientFinance.objects.get(
                pk=d["client_id"],
                entreprise_id=request.user.entreprise_id,
            )
        except ClientFinance.DoesNotExist:
            return Response({"detail": "Client introuvable."}, status=status.HTTP_404_NOT_FOUND)

        lieu = None
        lieu_id = d.get("lieu_id")
        if lieu_id:
            try:
                lieu = Lieu.objects.get(pk=lieu_id, entreprise_id=request.user.entreprise_id)
            except Lieu.DoesNotExist:
                return Response({"detail": "Lieu introuvable."}, status=status.HTTP_400_BAD_REQUEST)

        retrancher_caisse = d.get("retrancher_caisse", False)

        if retrancher_caisse:
            from core.models import CustomUser as CU
            # DAF et COMPTABLE sont bloqués par DafReadOnlyMixin sur l'action "create"
            # avant d'atteindre ce point → seuls SUPREME_ADMIN et ADMIN sont effectivement autorisés.
            ROLES_AUTORISES = {CU.ROLE_SUPREME_ADMIN, CU.ROLE_ADMIN}
            if request.user.role not in ROLES_AUTORISES:
                return Response(
                    {"detail": "Seul un super-admin ou admin peut retrancher la caisse."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            journal = creer_journal_creance(
                client=client,
                lieu=lieu,
                description=d["description"],
                montant_initial=d["montant_initial"],
                created_by=request.user,
                lignes=d.get("lignes") or [],
                reference=d.get("reference", ""),
                date_echeance=d.get("date_echeance"),
                notes=d.get("notes", ""),
                retrancher_caisse=retrancher_caisse,
            )
        except ErreurFinance as e:
            return _err(e)

        journal_qs = JournalCreance.objects.prefetch_related(
            "lignes__produit", "paiements"
        ).get(pk=journal.pk)
        resp_data = JournalCreanceSerializer(journal_qs).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def paiement(self, request, pk=None):
        journal = self.get_object()
        guard = IdempotencyGuard(request, "paiement_creance")
        early = guard.check()
        if early is not None:
            return early

        ser = PaiementCreanceCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            enregistrer_paiement_creance(
                journal=journal,
                montant=d["montant"],
                date=d["date"],
                created_by=request.user,
                mode_paiement=d.get("mode_paiement", "especes"),
                reference=d.get("reference", ""),
                notes=d.get("notes", ""),
            )
        except ErreurFinance as e:
            return _err(e)
        journal.refresh_from_db()
        resp_data = JournalCreanceSerializer(journal).data
        guard.success(resp_data)
        return Response(resp_data)

    @action(detail=True, methods=["post"])
    def solder(self, request, pk=None):
        journal = self.get_object()
        try:
            solder_journal_creance(journal=journal, created_by=request.user)
        except ErreurFinance as e:
            return _err(e)
        journal.refresh_from_db()
        return Response(JournalCreanceSerializer(journal).data)


# ═══════════════════════════════════════════════════════════════════════════════
# EMPRUNTS
# ═══════════════════════════════════════════════════════════════════════════════

class EmpruntViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    """
    GET  /api/finance/emprunts/                   — liste
    POST /api/finance/emprunts/                   — enregistrer emprunt
    GET  /api/finance/emprunts/{id}/              — détail + remboursements
    POST /api/finance/emprunts/{id}/remboursement/ — enregistrer remboursement
    """
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return Emprunt.objects.none()
        qs = Emprunt.objects.filter(
            entreprise_id=ent_id
        ).prefetch_related("remboursements")

        statut = self.request.query_params.get("statut")
        if statut in ("en_cours", "rembourse"):
            qs = qs.filter(statut=statut)

        return qs.order_by("-created_at")

    def get_serializer_class(self):
        return EmpruntSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)

        guard = IdempotencyGuard(request, "creer_emprunt")
        early = guard.check(success_status=status.HTTP_201_CREATED)
        if early is not None:
            return early

        ser = EmpruntCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            emprunt = creer_emprunt(
                entreprise=_get_entreprise(request),
                created_by=request.user,
                **d,
            )
        except ErreurFinance as e:
            return _err(e)
        resp_data = EmpruntSerializer(emprunt).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def remboursement(self, request, pk=None):
        emprunt = self.get_object()
        guard = IdempotencyGuard(request, "remboursement_emprunt")
        early = guard.check()
        if early is not None:
            return early

        ser = RemboursementCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            enregistrer_remboursement(
                emprunt=emprunt,
                montant=d["montant"],
                date=d["date"],
                created_by=request.user,
                reference=d.get("reference", ""),
                notes=d.get("notes", ""),
            )
        except ErreurFinance as e:
            return _err(e)
        emprunt.refresh_from_db()
        resp_data = EmpruntSerializer(emprunt).data
        guard.success(resp_data)
        return Response(resp_data)


# ═══════════════════════════════════════════════════════════════════════════════
# CAISSE SUPRÊME
# ═══════════════════════════════════════════════════════════════════════════════

class CaisseSupremeViewSet(DafReadOnlyMixin, ListModelMixin, CreateModelMixin, GenericViewSet):
    """
    GET  /api/finance/caisse/ — liste des mouvements + solde courant
    POST /api/finance/caisse/ — enregistrer dépôt ou retrait
    """
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return CaisseSupremeTransaction.objects.none()
        qs = CaisseSupremeTransaction.objects.filter(
            entreprise_id=ent_id
        ).select_related("created_by")

        type_t = self.request.query_params.get("type")
        if type_t in ("depot", "retrait"):
            qs = qs.filter(type_transaction=type_t)

        return qs.order_by("-date", "-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return CaisseTransactionCreateSerializer
        return CaisseTransactionSerializer

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            data = CaisseTransactionSerializer(page, many=True).data
            response = self.get_paginated_response(data)
            ent = _get_entreprise(request)
            response.data["solde_courant"] = str(get_solde_caisse(ent)) if ent else "0"
            return response
        data = CaisseTransactionSerializer(qs, many=True).data
        ent = _get_entreprise(request)
        return Response({
            "results": data,
            "solde_courant": str(get_solde_caisse(ent)) if ent else "0",
        })

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)

        guard = IdempotencyGuard(request, "transaction_caisse")
        early = guard.check(success_status=status.HTTP_201_CREATED)
        if early is not None:
            return early

        ser = CaisseTransactionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            t = enregistrer_transaction_caisse(
                entreprise=_get_entreprise(request),
                created_by=request.user,
                type_transaction=d["type_transaction"],
                montant=d["montant"],
                description=d["description"],
                date=d["date"],
                reference=d.get("reference", ""),
            )
        except ErreurFinance as e:
            return _err(e)
        resp_data = CaisseTransactionSerializer(t).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJETS
# ═══════════════════════════════════════════════════════════════════════════════

class ProjetViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, GenericViewSet):
    """
    GET  /api/finance/projets/               — liste
    POST /api/finance/projets/               — créer
    GET  /api/finance/projets/{id}/          — détail + dépenses + dépôts
    POST /api/finance/projets/{id}/depense/  — ajouter dépense
    POST /api/finance/projets/{id}/depot/    — ajouter fonds supplémentaires
    PATCH /api/finance/projets/{id}/statut/  — changer statut (en_cours/termine/suspendu)
    """
    permission_classes = [IsDafRole]
    throttle_classes = [FinanceCreateRateThrottle]

    def get_queryset(self):
        ent_id = self.request.user.entreprise_id
        if not ent_id:
            return Projet.objects.none()
        qs = Projet.objects.filter(
            entreprise_id=ent_id
        ).prefetch_related("depenses", "depots")

        statut = self.request.query_params.get("statut")
        if statut in ("en_cours", "termine", "suspendu"):
            qs = qs.filter(statut=statut)

        return qs.order_by("-created_at")

    def get_serializer_class(self):
        return ProjetSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)

        guard = IdempotencyGuard(request, "creer_projet")
        early = guard.check(success_status=status.HTTP_201_CREATED)
        if early is not None:
            return early

        ser = ProjetCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            projet = creer_projet(
                entreprise=_get_entreprise(request),
                created_by=request.user,
                nom=d["nom"],
                description=d.get("description", ""),
                budget_initial=d["budget_initial"],
                date_debut=d["date_debut"],
                date_fin=d.get("date_fin"),
            )
        except ErreurFinance as e:
            return _err(e)
        resp_data = ProjetSerializer(projet).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def depense(self, request, pk=None):
        projet = self.get_object()
        guard = IdempotencyGuard(request, "depense_projet")
        early = guard.check()
        if early is not None:
            return early

        ser = DepenseProjetCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            enregistrer_depense_projet(
                projet=projet,
                montant=d["montant"],
                description=d["description"],
                date=d["date"],
                created_by=request.user,
            )
        except ErreurFinance as e:
            return _err(e)
        projet.refresh_from_db()
        resp_data = ProjetSerializer(projet).data
        guard.success(resp_data)
        return Response(resp_data)

    @action(detail=True, methods=["post"])
    def depot(self, request, pk=None):
        projet = self.get_object()
        guard = IdempotencyGuard(request, "depot_projet")
        early = guard.check()
        if early is not None:
            return early

        ser = DepotProjetCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            enregistrer_depot_projet(
                projet=projet,
                montant=d["montant"],
                description=d["description"],
                date=d["date"],
                created_by=request.user,
            )
        except ErreurFinance as e:
            return _err(e)
        projet.refresh_from_db()
        resp_data = ProjetSerializer(projet).data
        guard.success(resp_data)
        return Response(resp_data)

    @action(detail=True, methods=["patch"])
    def changer_statut(self, request, pk=None):
        projet = self.get_object()
        nouveau_statut = request.data.get("statut")
        if nouveau_statut not in ("en_cours", "termine", "suspendu"):
            return Response(
                {"detail": "Statut invalide. Valeurs acceptées : en_cours, termine, suspendu."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        projet.statut = nouveau_statut
        projet.save(update_fields=["statut", "updated_at"])
        return Response(ProjetSerializer(projet).data)


# ═══════════════════════════════════════════════════════════════════════════════
# COLLECTE ARGENT — Passages du collectionneur
# ═══════════════════════════════════════════════════════════════════════════════

class CollecteViewSet(DafReadOnlyMixin, ListModelMixin, RetrieveModelMixin, CreateModelMixin, UpdateModelMixin, GenericViewSet):
    """
    GET   /api/finance/collectes/        — liste (filtrée par rôle)
    POST  /api/finance/collectes/        — enregistrer un passage
    GET   /api/finance/collectes/{id}/   — détail
    PATCH /api/finance/collectes/{id}/   — correction (montant_trouve/pris/notes)

    Isolation :
      - Collecteur : voit uniquement SES collectes (collecteur=request.user)
      - Admin / DAF / Comptable : voient toutes les collectes de l'entreprise
    Filtres (admin/DAF uniquement) : ?lieu_id= ?debut= ?fin= ?collecteur_id=
    """
    permission_classes = [IsDafRole | IsAdminRole | IsCollecteurRole | IsComptableRole]
    throttle_classes = [FinanceCreateRateThrottle]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        ent_id = user.entreprise_id
        if not ent_id:
            return CollecteArgent.objects.none()

        qs = CollecteArgent.objects.filter(
            lieu__entreprise_id=ent_id,
        ).select_related("lieu", "collecteur", "created_by", "depot_banque").order_by("-date_collecte", "-created_at")

        # Isolation stricte : le collecteur ne voit que ses propres collectes
        from core.models import CustomUser as CU
        if user.role == CU.ROLE_COLLECTEUR:
            qs = qs.filter(collecteur=user)
        else:
            # Admin/DAF peuvent filtrer par collecteur
            collecteur_id = self.request.query_params.get("collecteur_id")
            if collecteur_id:
                qs = qs.filter(collecteur_id=collecteur_id)

        lieu_id = self.request.query_params.get("lieu_id")
        if lieu_id:
            qs = qs.filter(lieu_id=lieu_id)

        debut = self.request.query_params.get("debut")
        fin   = self.request.query_params.get("fin")
        if debut:
            qs = qs.filter(date_collecte__gte=debut)
        if fin:
            qs = qs.filter(date_collecte__lte=fin)

        return qs

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return CollecteArgentUpdateSerializer
        return CollecteArgentSerializer

    def create(self, request, *args, **kwargs):
        guard = IdempotencyGuard(request, "collecte_create")
        early = guard.check(success_status=status.HTTP_201_CREATED)
        if early is not None:
            return early

        from core.models import CustomUser as CU
        if request.user.role != CU.ROLE_COLLECTEUR:
            return Response(
                {"detail": "Seul le collecteur peut enregistrer une collecte."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)

        ser = CollecteArgentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            lieu = Lieu.objects.get(
                pk=d["lieu_id"],
                entreprise_id=request.user.entreprise_id,
                type_lieu=Lieu.TYPE_MAGASIN,
            )
        except Lieu.DoesNotExist:
            return Response(
                {"detail": "Boutique introuvable ou non autorisée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            collecte = enregistrer_collecte(
                lieu=lieu,
                date_collecte=d["date_collecte"],
                montant_trouve=d["montant_trouve"],
                montant_pris=d["montant_pris"],
                collecteur=request.user,
                notes=d.get("notes", ""),
                created_by=request.user,
                deposer_en_banque=True,
                entreprise=request.user.entreprise,
            )
        except ErreurFinance as e:
            return _err(e)

        collecte_qs = CollecteArgent.objects.select_related(
            "lieu", "collecteur", "created_by", "depot_banque"
        ).get(pk=collecte.pk)
        resp_data = CollecteArgentSerializer(collecte_qs).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        collecte = self.get_object()

        # SÉCURITÉ : Interdiction stricte de modification des montants par le collecteur
        # Seul admin/DAF peuvent corriger avec audit log
        from core.models import CustomUser as CU
        if request.user.role == CU.ROLE_COLLECTEUR:
            # Le collecteur peut modifier uniquement les notes (pour corriger une faute de frappe)
            if any(k in request.data for k in ['montant_trouve', 'montant_pris']):
                return Response(
                    {"detail": "Collecteur : vous ne pouvez modifier que les notes. contactez admin pour corriger les montants."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # Modification notes uniquement
            ser = CollecteArgentUpdateSerializer(data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            if 'notes' in ser.validated_data:
                collecte.notes = ser.validated_data['notes']
                collecte.save(update_fields=['notes', 'updated_at'])
            return Response(CollecteArgentSerializer(collecte).data)

        # Pour admin/DAF : la correction nécessite une validation
        ser = CollecteArgentUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)

        from finance.services import modifier_collecte
        try:
            collecte = modifier_collecte(
                collecte=collecte,
                updated_by=request.user,
                **ser.validated_data,
            )
        except ErreurFinance as e:
            return _err(e)

        collecte_qs = CollecteArgent.objects.select_related(
            "lieu", "collecteur", "created_by", "depot_banque"
        ).get(pk=collecte.pk)
        return Response(CollecteArgentSerializer(collecte_qs).data)

    @action(detail=False, methods=["get"], url_path="caisse-disponible")
    def caisse_disponible(self, request):
        """
        GET /api/finance/collectes/caisse-disponible/?lieu_id=X
        Retourne la caisse physique disponible dans une boutique.
        Accessible par le collecteur (pour pré-valider son saisie).
        """
        lieu_id = request.query_params.get("lieu_id")
        if not lieu_id:
            return Response({"detail": "lieu_id requis."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)
        try:
            lieu = Lieu.objects.get(
                pk=lieu_id,
                entreprise_id=request.user.entreprise_id,
                type_lieu=Lieu.TYPE_MAGASIN,
            )
        except Lieu.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)
        caisse = get_caisse_physique_boutique(lieu)
        return Response({"lieu_id": lieu.pk, "lieu_nom": lieu.nom, "caisse_disponible": str(caisse)})

    @action(detail=False, methods=["get"], url_path="caisses-disponibles")
    def caisses_disponibles(self, request):
        """
        GET /api/finance/collectes/caisses-disponibles/
        Retourne la caisse physique disponible pour toutes les boutiques de l'entreprise
        en une seule requête (évite les N appels parallèles côté frontend).
        """
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)
        lieux = Lieu.objects.filter(
            entreprise_id=request.user.entreprise_id,
            type_lieu=Lieu.TYPE_MAGASIN,
        ).order_by("nom")
        result = [
            {"lieu_id": l.pk, "lieu_nom": l.nom, "caisse_disponible": str(get_caisse_physique_boutique(l))}
            for l in lieux
        ]
        return Response(result)


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD GLOBAL (Admin / DAF)
# ═══════════════════════════════════════════════════════════════════════════════

class DashboardGlobalView(APIView):
    """
    GET /api/finance/dashboard/
    Agrégats financiers globaux : ventes, cash, créances, dettes, dépenses, bénéfices.
    Accessible uniquement par admin et DAF.
    """
    permission_classes = [IsDafRole | IsAdminRole]

    def get(self, request):
        if not request.user.entreprise_id:
            return Response({"detail": "Entreprise requise."}, status=status.HTTP_403_FORBIDDEN)
        data = get_dashboard_global(request.user.entreprise)
        ser  = DashboardGlobalSerializer(data)
        return Response(ser.data)
