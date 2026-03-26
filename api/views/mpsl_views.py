"""
API MPSL KONIS : achats avec impact stock, transferts vers usines/magasins.
Le dépôt MPSL est un centre logistique d'approvisionnement (pas de production, pas de ventes).
"""
from decimal import Decimal

from django.db.models import Sum
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from api.permissions import IsMPSLRole
from api.serializers import (
    AchatMPSLBatchSerializer,
    AchatMPSLCreateSerializer,
    AchatMPSLSerializer,
    StockSerializer,
    TransfertMPSLCreateSerializer,
    TransfertSerializer,
)
from api.throttling import UsineCreateRateThrottle
from api.utils import filter_by_date, get_lieu_mpsl
from audit.services import audit_log
from core.models import CustomUser, Lieu
from inventaire.models import AchatMPSL, Stock, Transfert
from inventaire.services import ErreurStock, enregistrer_achat_mpsl, enregistrer_achats_mpsl_batch, transfert_depuis_mpsl
from produits.models import Produit


# --- Catalogue produits (lecture seule, scoped entreprise) --------------------

class CatalogueProduitsMPSLView(APIView):
    """GET /api/mpsl/catalogue/ : liste des produits de l'entreprise pour les transferts."""
    permission_classes = [IsAuthenticated, IsMPSLRole]

    def get(self, request):
        ent_id = request.user.entreprise_id
        if not ent_id:
            return Response([])
        produits = Produit.objects.filter(
            entreprise_id=ent_id
        ).order_by("nom").values("id", "nom", "code", "unite")
        return Response(list(produits))


# --- Achats MPSL (avec impact stock) -----------------------------------------

class AchatMPSLViewSet(ModelViewSet):
    """
    GET  /api/mpsl/achats/ : historique des achats du dépôt MPSL.
    POST /api/mpsl/achats/ : enregistrer un achat (impacte le stock).
    """
    serializer_class = AchatMPSLSerializer
    permission_classes = [IsAuthenticated, IsMPSLRole]
    throttle_classes = [UsineCreateRateThrottle]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = AchatMPSL.objects.select_related(
            "lieu", "created_by", "fournisseur", "journal_payable"
        ).order_by("-date")
        lieu = get_lieu_mpsl(self.request)
        if self.request.user.role == CustomUser.ROLE_MPSL:
            return qs.filter(lieu=lieu) if lieu else qs.none()
        # Admin : toujours scoper par entreprise — jamais retourner toute la table
        if not self.request.user.entreprise_id:
            return qs.none()
        if lieu:
            return qs.filter(lieu=lieu)
        qs = qs.filter(lieu__entreprise_id=self.request.user.entreprise_id)
        qs = filter_by_date(qs, self.request)
        return qs

    def create(self, request, *args, **kwargs):
        from api.idempotency import IdempotencyGuard
        guard = IdempotencyGuard(request, "achat_mpsl")
        early = guard.check(success_status=status.HTTP_201_CREATED, required=False)
        if early is not None:
            return early

        lieu = get_lieu_mpsl(request)
        if not lieu:
            return Response(
                {"detail": "Dépôt MPSL introuvable pour ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = AchatMPSLCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        # Résoudre le fournisseur (scoping multi-tenant)
        fournisseur = None
        fournisseur_id = d.get("fournisseur_id")
        if fournisseur_id:
            from finance.models import Creancier
            try:
                fournisseur = Creancier.objects.get(
                    pk=fournisseur_id,
                    entreprise_id=lieu.entreprise_id,
                )
            except Creancier.DoesNotExist:
                return Response(
                    {"detail": "Fournisseur introuvable ou non autorisé."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            achat = enregistrer_achat_mpsl(
                lieu=lieu,
                produit_nom=d["produit_nom"],
                quantite=d["quantite"],
                unite=d["unite"],
                prix_unitaire=d.get("prix_unitaire", Decimal("0")),
                notes=d.get("notes", ""),
                created_by=request.user,
                fournisseur=fournisseur,
                type_paiement=d.get("type_paiement", "cash"),
                montant_paye_initial=d.get("montant_paye_initial", Decimal("0")),
                poids_par_sac=d.get("poids_par_sac"),
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        audit_log(
            user=request.user,
            action="achat_mpsl_cree",
            object_type="achat_mpsl",
            object_id=achat.pk,
            extra={
                "lieu": lieu.nom,
                "produit_nom": achat.produit_nom,
                "quantite": str(achat.quantite),
                "prix_total": str(achat.prix_total),
            },
            request=request,
        )
        resp_data = AchatMPSLSerializer(achat).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)


# --- Achat groupé (multi-produits, un seul JournalPayable) --------------------

class AchatMPSLBatchView(APIView):
    """
    POST /api/mpsl/achats/batch/
    Crée plusieurs AchatMPSL en une seule transaction atomique.
    Un seul JournalPayable pour l'ensemble du bon de commande.

    Body :
      {
        "type_paiement": "cash"|"credit"|"partiel",
        "fournisseur_id": <int|null>,       # Créancier existant
        "fournisseur_nom": "<str>",         # OU créer un nouveau fournisseur
        "acompte": <int>,                   # si partiel
        "produits": [
          { "produit_nom": "...", "quantite": <int>, "unite": "sacs"|"kg"|"tonnes",
            "poids_par_sac": <float|null>, "prix_unitaire": <int>, "notes": "..." },
          ...
        ]
      }
    """
    permission_classes = [IsAuthenticated, IsMPSLRole]
    throttle_classes = [UsineCreateRateThrottle]

    def post(self, request):
        from api.idempotency import IdempotencyGuard
        guard = IdempotencyGuard(request, "achat_mpsl_batch")
        early = guard.check(success_status=status.HTTP_201_CREATED, required=False)
        if early is not None:
            return early

        lieu = get_lieu_mpsl(request)
        if not lieu:
            return Response(
                {"detail": "Dépôt MPSL introuvable pour ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = AchatMPSLBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        # ── Résoudre le fournisseur ────────────────────────────────────────────
        fournisseur = None
        tp = d["type_paiement"]
        fournisseur_id = d.get("fournisseur_id")
        fournisseur_nom = (d.get("fournisseur_nom") or "").strip()

        if tp in ("credit", "partiel"):
            if fournisseur_id:
                from finance.models import Creancier
                try:
                    fournisseur = Creancier.objects.get(
                        pk=fournisseur_id,
                        entreprise_id=lieu.entreprise_id,
                    )
                except Creancier.DoesNotExist:
                    return Response(
                        {"detail": "Fournisseur introuvable ou non autorisé."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif fournisseur_nom:
                # Créer le fournisseur à la volée
                from finance.models import Creancier
                fournisseur, created = Creancier.objects.get_or_create(
                    nom__iexact=fournisseur_nom,
                    entreprise_id=lieu.entreprise_id,
                    defaults={"nom": fournisseur_nom, "entreprise_id": lieu.entreprise_id},
                )
                if created:
                    audit_log(
                        user=request.user,
                        action="fournisseur_cree_inline",
                        object_type="Creancier",
                        object_id=fournisseur.pk,
                        extra={"nom": fournisseur.nom, "source": "achat_batch"},
                        request=request,
                    )
            else:
                return Response(
                    {"detail": "Fournisseur requis pour achat à crédit ou partiel."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            achats = enregistrer_achats_mpsl_batch(
                lieu=lieu,
                produits=d["produits"],
                type_paiement=tp,
                fournisseur=fournisseur,
                acompte=d.get("acompte", Decimal("0")),
                created_by=request.user,
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        audit_log(
            user=request.user,
            action="achat_mpsl_batch_cree",
            object_type="AchatMPSL",
            object_id=achats[0].pk if achats else None,
            extra={
                "lieu": lieu.nom,
                "nb_produits": len(achats),
                "type_paiement": tp,
                "fournisseur": fournisseur.nom if fournisseur else None,
                "total": str(sum(a.prix_total for a in achats)),
            },
            request=request,
        )

        resp_data = AchatMPSLSerializer(achats, many=True).data
        guard.success({"achats": list(resp_data)})
        return Response(resp_data, status=status.HTTP_201_CREATED)


# --- Transferts depuis MPSL ---------------------------------------------------

class TransfertMPSLViewSet(ModelViewSet):
    """
    GET  /api/mpsl/transferts/ : historique des transferts sortants du dépôt MPSL.
    POST /api/mpsl/transferts/ : créer un transfert vers une usine ou un magasin.
    """
    serializer_class = TransfertSerializer
    permission_classes = [IsAuthenticated, IsMPSLRole]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Transfert.objects.select_related(
            "from_lieu", "to_lieu"
        ).prefetch_related("mouvements__produit").filter(
            from_lieu__type_lieu=Lieu.TYPE_MPSL
        ).order_by("-date")

        lieu = get_lieu_mpsl(self.request)
        if self.request.user.role == CustomUser.ROLE_MPSL:
            return qs.filter(from_lieu=lieu) if lieu else qs.none()
        # Admin : toujours scoper par entreprise — jamais retourner toute la table
        if not self.request.user.entreprise_id:
            return qs.none()
        if lieu:
            return qs.filter(from_lieu=lieu)
        qs = qs.filter(from_lieu__entreprise_id=self.request.user.entreprise_id)
        qs = filter_by_date(qs, self.request)
        return qs

    def create(self, request, *args, **kwargs):
        from api.idempotency import IdempotencyGuard
        guard = IdempotencyGuard(request, "transfert_mpsl")
        early = guard.check(success_status=status.HTTP_201_CREATED, required=False)
        if early is not None:
            return early

        from_lieu = get_lieu_mpsl(request)
        if not from_lieu:
            return Response(
                {"detail": "Dépôt MPSL introuvable pour ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = TransfertMPSLCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        to_lieu = d["to_lieu"]

        # Construire les lignes (produit, quantite) — pas de prix
        lignes_raw = d["lignes"]
        lignes = []
        for item in lignes_raw:
            produit_id = item.get("produit_id") or item.get("produit")
            try:
                produit = Produit.objects.get(pk=produit_id, entreprise=from_lieu.entreprise)
            except Produit.DoesNotExist:
                return Response(
                    {"detail": f"Produit {produit_id} introuvable dans ce dépôt."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quantite = Decimal(str(item["quantite"]))
            raw_unite = (item.get("unite") or "").strip().lower()
            if raw_unite and raw_unite not in ("sac", "sacs", "kg", "tonne", "tonnes"):
                return Response(
                    {"detail": f"Unit?? invalide pour {produit.nom} : '{raw_unite}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            unite_ligne = raw_unite or (produit.unite or "kg")
            lignes.append((produit, quantite, unite_ligne))

        try:
            transfert = transfert_depuis_mpsl(
                from_mpsl=from_lieu,
                to_lieu=to_lieu,
                lignes=lignes,
                updated_by=request.user,
                log_request=request,
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        audit_log(
            user=request.user,
            action="transfert_mpsl_cree",
            object_type="transfert",
            object_id=transfert.pk,
            extra={
                "from_lieu": from_lieu.nom,
                "to_lieu": to_lieu.nom,
                "nb_lignes": len(lignes),
            },
            request=request,
        )
        resp_data = TransfertSerializer(transfert).data
        guard.success(resp_data)
        return Response(resp_data, status=status.HTTP_201_CREATED)


# --- Stock MPSL ---------------------------------------------------------------

class StockMPSLView(APIView):
    """GET /api/mpsl/stock/ : stock actuel du dépôt MPSL.

    Calcule depuis la source primaire (lecture seule, aucune écriture) :
        restant = Σ(AchatMPSL) − Σ(MouvementStock déjà transférés depuis ce MPSL)
    """
    permission_classes = [IsAuthenticated, IsMPSLRole]

    def get(self, request):
        lieu = get_lieu_mpsl(request)
        if not lieu:
            if request.user.role == CustomUser.ROLE_ADMIN:
                return Response([])
            return Response(
                {"detail": "Dépôt MPSL introuvable pour ce compte."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from inventaire.models import MouvementStock

        def _d(val):
            return Decimal(str(val)) if val is not None else Decimal("0")

        # Tous les noms de produits ayant des achats enregistrés pour ce dépôt
        noms = (
            AchatMPSL.objects.filter(lieu=lieu)
            .values_list("produit_nom", flat=True)
            .distinct()
            .order_by("produit_nom")
        )

        result = []
        for nom in noms:
            produit = Produit.objects.filter(
                nom__iexact=nom,
                entreprise_id=lieu.entreprise_id,
            ).first()
            if produit is None:
                continue

            produit_unite = (produit.unite or "kg").strip().lower()
            stock_obj = Stock.objects.filter(produit=produit, lieu=lieu).first()

            if produit_unite in ("sac", "sacs"):
                # Produits en sacs : la table Stock est la source de vérité.
                # _prelever_stock_unite gère correctement sacs, kg convertis et
                # auto-conversions — MouvementStock.quantite peut être en sacs OU
                # en kg selon le type de transfert, donc on ne peut pas soustraire
                # directement les AchatMPSL sacs. La table Stock est toujours juste.
                quantite_sac = _d(stock_obj.quantite)    if stock_obj else Decimal("0")
                quantite_kg  = _d(stock_obj.quantite_kg) if stock_obj else Decimal("0")
                if quantite_sac <= 0 and quantite_kg <= 0:
                    continue
                result.append({
                    "produit_id": produit.id,
                    "produit_nom": produit.nom,
                    "produit_code": produit.code or "",
                    "quantite": str(quantite_sac),
                    "quantite_kg": str(quantite_kg),
                    "poids_par_sac": str(produit.poids_par_sac) if produit.poids_par_sac is not None else None,
                    "unite": produit.unite,
                })
            else:
                # Produits en kg : MouvementStock.quantite est toujours en kg pour
                # les produits kg (_valider_unite_transfert n'autorise que kg/tonnes).
                # Stock.quantite_kg peut être désynchronisé → on calcule depuis la source.
                achats_qs = AchatMPSL.objects.filter(lieu=lieu, produit_nom__iexact=produit.nom)
                pps = produit.poids_par_sac or Decimal("0")
                total_kg_in = (
                    _d(achats_qs.filter(unite="kg").aggregate(s=Sum("quantite"))["s"])
                    + _d(achats_qs.filter(unite__in=("tonne", "tonnes")).aggregate(s=Sum("quantite"))["s"]) * Decimal("1000")
                    + _d(achats_qs.filter(unite__in=("sac", "sacs")).aggregate(s=Sum("quantite"))["s"]) * pps
                )
                deja_transfere = _d(
                    MouvementStock.objects.filter(
                        produit=produit,
                        transfert__from_lieu=lieu,
                        transfert__to_lieu__type_lieu__in=(Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE),
                    ).aggregate(s=Sum("quantite"))["s"]
                )
                restant_kg = max(Decimal("0"), total_kg_in - deja_transfere)
                if restant_kg <= 0:
                    continue
                result.append({
                    "produit_id": produit.id,
                    "produit_nom": produit.nom,
                    "produit_code": produit.code or "",
                    "quantite": "0",
                    "quantite_kg": str(restant_kg),
                    "poids_par_sac": str(produit.poids_par_sac) if produit.poids_par_sac is not None else None,
                    "unite": produit.unite,
                })

        return Response(result)


# --- Conversion sacs → kg (MPSL) ---------------------------------------------

class ConvertirSacEnKgMpslView(APIView):
    """
    POST /api/mpsl/stock/<produit_id>/convertir/
    Convertit N sacs entiers en kg pour le stock MPSL.
    Body : { "nombre_sacs": <int> }
    """
    permission_classes = [IsAuthenticated, IsMPSLRole]

    def post(self, request, produit_id):
        from inventaire.services import convertir_sac_en_kg
        from decimal import InvalidOperation
        from api.idempotency import IdempotencyGuard

        guard = IdempotencyGuard(request, "conversion_sac_en_kg")
        early = guard.check()
        if early is not None:
            return early

        lieu = get_lieu_mpsl(request)
        if not lieu:
            return Response({"detail": "Dépôt MPSL introuvable."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            stock = Stock.objects.get(produit_id=produit_id, lieu=lieu)
        except Stock.DoesNotExist:
            return Response({"detail": "Stock introuvable."}, status=status.HTTP_404_NOT_FOUND)

        nombre_sacs = request.data.get("nombre_sacs")
        try:
            nombre_sacs = int(nombre_sacs)
        except (TypeError, ValueError):
            return Response({"detail": "nombre_sacs doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)

        poids_par_sac_override = None
        pps_raw = request.data.get("poids_par_sac")
        if pps_raw is not None:
            try:
                poids_par_sac_override = Decimal(str(pps_raw))
                if poids_par_sac_override <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                return Response({"detail": "poids_par_sac doit être un nombre positif."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            kg = convertir_sac_en_kg(
                stock=stock,
                nombre_sacs=nombre_sacs,
                updated_by=request.user,
                poids_par_sac_override=poids_par_sac_override,
                log_request=request,
            )
        except ErreurStock as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        stock.refresh_from_db()
        resp_data = {
            "kg_generes": str(kg),
            "quantite_sacs": str(stock.quantite),
            "quantite_kg": str(stock.quantite_kg),
        }
        guard.success(resp_data)
        return Response(resp_data)


# --- Fournisseurs (lecture seule pour les achats MPSL) ------------------------

class FournisseursMpslView(APIView):
    """GET /api/mpsl/fournisseurs/?search=... — creanciers de l'entreprise (lecture seule)."""
    permission_classes = [IsAuthenticated, IsMPSLRole]

    def get(self, request):
        from django.db.models import Q
        from finance.models import Creancier
        from api.serializers_finance import CreancierSerializer
        ent_id = request.user.entreprise_id
        if not ent_id:
            return Response([])
        qs = Creancier.objects.filter(entreprise_id=ent_id).order_by("nom")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(nom__icontains=search) | Q(contact__icontains=search))
        return Response(CreancierSerializer(qs[:30], many=True).data)


# --- Dashboard MPSL -----------------------------------------------------------

class MpslDashboardView(APIView):
    """GET /api/mpsl/dashboard/ : résumé du dépôt MPSL."""
    permission_classes = [IsAuthenticated, IsMPSLRole]

    def get(self, request):
        lieu = get_lieu_mpsl(request)
        if not lieu:
            if request.user.role == CustomUser.ROLE_ADMIN:
                return Response({
                    "lieu": "Admin (aucun dépôt MPSL sélectionné)",
                    "stock_mpsl": [],
                    "total_achats_fcfa": "0",
                    "total_transferts": "0",
                    "last_achats": [],
                    "last_transferts": [],
                })
            return Response(
                {"detail": "Dépôt MPSL introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Réutilise la même logique de calcul que StockMPSLView (lecture seule)
        from inventaire.models import MouvementStock

        def _d(val):
            return Decimal(str(val)) if val is not None else Decimal("0")

        noms = (
            AchatMPSL.objects.filter(lieu=lieu)
            .values_list("produit_nom", flat=True)
            .distinct()
        )
        stock_items = []
        for nom in noms:
            produit = Produit.objects.filter(
                nom__iexact=nom, entreprise_id=lieu.entreprise_id
            ).first()
            if produit is None:
                continue
            produit_unite = (produit.unite or "kg").strip().lower()
            stock_obj = Stock.objects.filter(produit=produit, lieu=lieu).first()
            if produit_unite in ("sac", "sacs"):
                quantite_sac = _d(stock_obj.quantite)    if stock_obj else Decimal("0")
                quantite_kg  = _d(stock_obj.quantite_kg) if stock_obj else Decimal("0")
                if quantite_sac <= 0 and quantite_kg <= 0:
                    continue
            else:
                achats_qs = AchatMPSL.objects.filter(lieu=lieu, produit_nom__iexact=produit.nom)
                pps = produit.poids_par_sac or Decimal("0")
                total_kg_in = (
                    _d(achats_qs.filter(unite="kg").aggregate(s=Sum("quantite"))["s"])
                    + _d(achats_qs.filter(unite__in=("tonne", "tonnes")).aggregate(s=Sum("quantite"))["s"]) * Decimal("1000")
                    + _d(achats_qs.filter(unite__in=("sac", "sacs")).aggregate(s=Sum("quantite"))["s"]) * pps
                )
                deja_transfere = _d(
                    MouvementStock.objects.filter(
                        produit=produit,
                        transfert__from_lieu=lieu,
                        transfert__to_lieu__type_lieu__in=(Lieu.TYPE_MAGASIN, Lieu.TYPE_USINE),
                    ).aggregate(s=Sum("quantite"))["s"]
                )
                quantite_sac = Decimal("0")
                quantite_kg  = max(Decimal("0"), total_kg_in - deja_transfere)
                if quantite_kg <= 0:
                    continue
            stock_items.append({
                "produit": produit.nom,
                "quantite": str(quantite_sac),
                "quantite_kg": str(quantite_kg),
                "poids_par_sac": str(produit.poids_par_sac) if produit.poids_par_sac is not None else None,
                "unite": produit.unite,
            })

        last_achats = AchatMPSL.objects.filter(lieu=lieu).order_by("-date")[:5]
        last_transferts = (
            Transfert.objects.filter(from_lieu=lieu)
            .select_related("to_lieu")
            .prefetch_related("mouvements__produit")
            .order_by("-date")[:5]
        )
        total_achats = AchatMPSL.objects.filter(lieu=lieu).aggregate(t=Sum("prix_total"))["t"] or 0
        total_transferts = Transfert.objects.filter(from_lieu=lieu).count()

        return Response({
            "lieu": lieu.nom,
            "stock_mpsl": stock_items,
            "total_achats_fcfa": str(total_achats),
            "total_transferts": total_transferts,
            "last_achats": [
                {
                    "id": a.id,
                    "produit": a.produit_nom,
                    "quantite": str(a.quantite),
                    "unite": a.unite,
                    "prix_total": str(a.prix_total),
                    "date": a.date.isoformat(),
                }
                for a in last_achats
            ],
            "last_transferts": [
                {
                    "id": t.id,
                    "to_lieu": t.to_lieu.nom,
                    "to_lieu_type": t.to_lieu.type_lieu,
                    "nb_produits": t.mouvements.count(),
                    "date": t.date.isoformat(),
                }
                for t in last_transferts
            ],
        })
