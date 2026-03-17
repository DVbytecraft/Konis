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
from inventaire.services import ErreurStock, enregistrer_achat_mpsl, transfert_depuis_mpsl
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
            "lieu", "created_by"
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
        lieu = get_lieu_mpsl(request)
        if not lieu:
            return Response(
                {"detail": "Dépôt MPSL introuvable pour ce compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = AchatMPSLCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            achat = enregistrer_achat_mpsl(
                lieu=lieu,
                produit_nom=d["produit_nom"],
                quantite=d["quantite"],
                unite=d["unite"],
                prix_unitaire=d.get("prix_unitaire", Decimal("0")),
                notes=d.get("notes", ""),
                created_by=request.user,
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
        )
        return Response(AchatMPSLSerializer(achat).data, status=status.HTTP_201_CREATED)


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
            lignes.append((produit, quantite))

        try:
            transfert = transfert_depuis_mpsl(
                from_mpsl=from_lieu,
                to_lieu=to_lieu,
                lignes=lignes,
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
        )
        return Response(TransfertSerializer(transfert).data, status=status.HTTP_201_CREATED)


# --- Stock MPSL ---------------------------------------------------------------

class StockMPSLView(APIView):
    """GET /api/mpsl/stock/ : stock actuel du dépôt MPSL."""
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
        stocks = (
            Stock.objects.filter(lieu=lieu)
            .select_related("produit")
            .order_by("produit__nom")
        )
        return Response([
            {
                "produit_id": s.produit_id,
                "produit_nom": s.produit.nom,
                "produit_code": s.produit.code or "",
                "quantite": str(s.quantite),
                "unite": s.produit.unite,
            }
            for s in stocks
        ])


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

        stock_mpsl = Stock.objects.filter(lieu=lieu).select_related("produit")
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
            "stock_mpsl": [
                {
                    "produit": s.produit.nom,
                    "quantite": str(s.quantite),
                    "unite": s.produit.unite,
                }
                for s in stock_mpsl
            ],
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
