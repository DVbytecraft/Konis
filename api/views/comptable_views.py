"""
API Comptable : lecture (ventes, dépenses, stock, transferts, achats usine). Filtre par lieu ?lieu=id.
Rapport par lieu avec filtres date ?debut=YYYY-MM-DD&fin=YYYY-MM-DD.

Sécurité IDOR : toutes les requêtes sont filtrées par request.user.entreprise
pour empêcher l'accès aux données d'une autre entreprise.

Performance : les calculs de totaux utilisent des agrégations SQL (Sum/annotate)
au lieu de boucles Python, évitant les problèmes N+1 et les chargements en mémoire.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from api.permissions import IsComptableRole
from api.serializers import (
    AchatUsineSerializer,
    DepenseSerializer,
    StockSerializer,
    TicketSerializer,
    TransfertSerializer,
)
from core.models import Lieu
from depenses.models import Depense
from inventaire.models import AchatUsine, Stock, Transfert
from usine.models import TransfertCession, TransfertInterUsine
from ventes.models import LigneVente, Ticket

# Expressions réutilisées pour calculer les montants en SQL (évite les boucles Python)
_VENTE_MONTANT = ExpressionWrapper(
    F("quantite") * F("prix_unitaire"),
    output_field=DecimalField(max_digits=18, decimal_places=2),
)
_CESSION_MONTANT = ExpressionWrapper(
    F("quantite_sacs") * F("prix_par_sac"),
    output_field=DecimalField(max_digits=18, decimal_places=2),
)


def _filter_by_lieu(qs, request, lieu_field="lieu"):
    lieu_id = request.query_params.get("lieu")
    if lieu_id:
        return qs.filter(**{f"{lieu_field}": lieu_id})
    return qs


def _filter_by_date(qs, request, date_field="date"):
    debut = request.query_params.get("debut")
    fin = request.query_params.get("fin")
    if debut:
        qs = qs.filter(**{f"{date_field}__date__gte": debut})
    if fin:
        qs = qs.filter(**{f"{date_field}__date__lte": fin})
    return qs


class StockComptableViewSet(ReadOnlyModelViewSet):
    queryset = Stock.objects.all().select_related("produit", "lieu")
    serializer_class = StockSerializer
    permission_classes = [IsComptableRole]

    def get_queryset(self):
        qs = super().get_queryset().filter(lieu__entreprise=self.request.user.entreprise)
        return _filter_by_lieu(qs, self.request)


class TransfertComptableViewSet(ReadOnlyModelViewSet):
    queryset = Transfert.objects.all().select_related("from_lieu", "to_lieu").prefetch_related("mouvements__produit").order_by("-date")
    serializer_class = TransfertSerializer
    permission_classes = [IsComptableRole]

    def get_queryset(self):
        qs = super().get_queryset().filter(from_lieu__entreprise=self.request.user.entreprise)
        qs = _filter_by_date(qs, self.request, "date")
        lieu_id = self.request.query_params.get("lieu")
        if lieu_id:
            qs = qs.filter(from_lieu_id=lieu_id) | qs.filter(to_lieu_id=lieu_id)
        return qs.distinct()


class TicketComptableViewSet(ReadOnlyModelViewSet):
    queryset = Ticket.objects.all().select_related("lieu").prefetch_related("lignes__produit").order_by("-date")
    serializer_class = TicketSerializer
    permission_classes = [IsComptableRole]

    def get_queryset(self):
        qs = super().get_queryset().filter(lieu__entreprise=self.request.user.entreprise)
        qs = _filter_by_lieu(qs, self.request)
        qs = _filter_by_date(qs, self.request)
        return qs


class DepenseComptableViewSet(ReadOnlyModelViewSet):
    queryset = Depense.objects.all().select_related("lieu", "categorie").order_by("-date")
    serializer_class = DepenseSerializer
    permission_classes = [IsComptableRole]

    def get_queryset(self):
        qs = super().get_queryset().filter(lieu__entreprise=self.request.user.entreprise)
        qs = _filter_by_lieu(qs, self.request)
        qs = _filter_by_date(qs, self.request)
        return qs


class AchatUsineComptableViewSet(ReadOnlyModelViewSet):
    """GET /api/comptable/achats-usine/ : lecture seule des achats usine."""
    queryset = AchatUsine.objects.all().select_related("lieu", "created_by").order_by("-date")
    serializer_class = AchatUsineSerializer
    permission_classes = [IsComptableRole]

    def get_queryset(self):
        qs = super().get_queryset().filter(lieu__entreprise=self.request.user.entreprise)
        qs = _filter_by_lieu(qs, self.request)
        qs = _filter_by_date(qs, self.request)
        return qs


# ---- Rapports par lieu ----

class RapportBoutiquesView(APIView):
    """
    GET /api/comptable/rapport-boutiques/
    Résumé par boutique : ventes (tickets) + cessions reçues.
    Filtres : ?debut=YYYY-MM-DD&fin=YYYY-MM-DD
    Performance : agrégations SQL au lieu de boucles Python.
    """
    permission_classes = [IsComptableRole]

    def get(self, request):
        entreprise = request.user.entreprise
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")

        # Initialiser toutes les boutiques de l'entreprise
        boutiques = {
            l.id: {
                "lieu_id": l.id, "lieu_nom": l.nom,
                "nb_tickets": 0, "total_ventes": Decimal("0"),
                "cessions_recues_sacs": Decimal("0"), "cessions_recues_montant": Decimal("0"),
            }
            for l in Lieu.objects.filter(type_lieu=Lieu.TYPE_MAGASIN, entreprise=entreprise)
        }

        # Agrégation SQL des ventes par boutique (1 query au lieu de N)
        lignes_qs = LigneVente.objects.filter(
            ticket__lieu__type_lieu=Lieu.TYPE_MAGASIN,
            ticket__lieu__entreprise=entreprise,
        )
        if debut:
            lignes_qs = lignes_qs.filter(ticket__date__date__gte=debut)
        if fin:
            lignes_qs = lignes_qs.filter(ticket__date__date__lte=fin)

        ticket_stats = (
            lignes_qs
            .values("ticket__lieu_id")
            .annotate(
                nb_tickets=Count("ticket", distinct=True),
                total_ventes=Sum(_VENTE_MONTANT),
            )
        )
        for stat in ticket_stats:
            bid = stat["ticket__lieu_id"]
            if bid in boutiques:
                boutiques[bid]["nb_tickets"] = stat["nb_tickets"] or 0
                boutiques[bid]["total_ventes"] = stat["total_ventes"] or Decimal("0")

        # Agrégation SQL des cessions reçues par boutique
        cessions_qs = TransfertCession.objects.filter(
            boutique__type_lieu=Lieu.TYPE_MAGASIN,
            boutique__entreprise=entreprise,
        )
        if debut:
            cessions_qs = cessions_qs.filter(created_at__date__gte=debut)
        if fin:
            cessions_qs = cessions_qs.filter(created_at__date__lte=fin)

        cession_stats = (
            cessions_qs
            .values("boutique_id")
            .annotate(
                total_sacs=Sum("quantite_sacs"),
                total_montant=Sum(_CESSION_MONTANT),
            )
        )
        for stat in cession_stats:
            bid = stat["boutique_id"]
            if bid in boutiques:
                boutiques[bid]["cessions_recues_sacs"] = stat["total_sacs"] or Decimal("0")
                boutiques[bid]["cessions_recues_montant"] = stat["total_montant"] or Decimal("0")

        result = [
            {
                **v,
                "total_ventes": str(v["total_ventes"]),
                "cessions_recues_sacs": str(v["cessions_recues_sacs"]),
                "cessions_recues_montant": str(v["cessions_recues_montant"]),
            }
            for v in boutiques.values()
        ]
        return Response(result)


class RapportUsinesView(APIView):
    """
    GET /api/comptable/rapport-usines/
    Résumé par usine : achats + transferts sortants (boutiques + inter-usines).
    Filtres : ?debut=YYYY-MM-DD&fin=YYYY-MM-DD
    Performance : agrégations SQL au lieu de boucles Python.
    """
    permission_classes = [IsComptableRole]

    def get(self, request):
        entreprise = request.user.entreprise
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")

        # Initialiser toutes les usines de l'entreprise
        usines = {
            l.id: {
                "lieu_id": l.id, "lieu_nom": l.nom,
                "nb_achats": 0, "total_achats": Decimal("0"),
                "transferts_boutiques_sacs": Decimal("0"), "transferts_boutiques_montant": Decimal("0"),
                "transferts_inter_usines_sacs": Decimal("0"), "transferts_inter_usines_montant": Decimal("0"),
            }
            for l in Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE, entreprise=entreprise)
        }

        # Agrégation SQL des achats par usine
        achats_qs = AchatUsine.objects.filter(lieu__type_lieu=Lieu.TYPE_USINE, lieu__entreprise=entreprise)
        if debut:
            achats_qs = achats_qs.filter(date__date__gte=debut)
        if fin:
            achats_qs = achats_qs.filter(date__date__lte=fin)

        achat_stats = (
            achats_qs
            .values("lieu_id")
            .annotate(nb_achats=Count("id"), total_achats=Sum("prix_total"))
        )
        for stat in achat_stats:
            uid = stat["lieu_id"]
            if uid in usines:
                usines[uid]["nb_achats"] = stat["nb_achats"] or 0
                usines[uid]["total_achats"] = stat["total_achats"] or Decimal("0")

        # Agrégation SQL des cessions par usine source
        cessions_qs = TransfertCession.objects.filter(lot__lieu_usine__entreprise=entreprise)
        if debut:
            cessions_qs = cessions_qs.filter(created_at__date__gte=debut)
        if fin:
            cessions_qs = cessions_qs.filter(created_at__date__lte=fin)

        cession_stats = (
            cessions_qs
            .values("lot__lieu_usine_id")
            .annotate(
                total_sacs=Sum("quantite_sacs"),
                total_montant=Sum(_CESSION_MONTANT),
            )
        )
        for stat in cession_stats:
            uid = stat["lot__lieu_usine_id"]
            if uid in usines:
                usines[uid]["transferts_boutiques_sacs"] = stat["total_sacs"] or Decimal("0")
                usines[uid]["transferts_boutiques_montant"] = stat["total_montant"] or Decimal("0")

        # Agrégation SQL des transferts inter-usines
        inter_qs = TransfertInterUsine.objects.filter(lot__lieu_usine__entreprise=entreprise)
        if debut:
            inter_qs = inter_qs.filter(created_at__date__gte=debut)
        if fin:
            inter_qs = inter_qs.filter(created_at__date__lte=fin)

        inter_stats = (
            inter_qs
            .values("lot__lieu_usine_id")
            .annotate(
                total_sacs=Sum("quantite_sacs"),
                total_montant=Sum(_CESSION_MONTANT),
            )
        )
        for stat in inter_stats:
            uid = stat["lot__lieu_usine_id"]
            if uid in usines:
                usines[uid]["transferts_inter_usines_sacs"] = stat["total_sacs"] or Decimal("0")
                usines[uid]["transferts_inter_usines_montant"] = stat["total_montant"] or Decimal("0")

        result = []
        for v in usines.values():
            total_transferts = v["transferts_boutiques_montant"] + v["transferts_inter_usines_montant"]
            result.append({
                **v,
                "total_achats": str(v["total_achats"]),
                "transferts_boutiques_sacs": str(v["transferts_boutiques_sacs"]),
                "transferts_boutiques_montant": str(v["transferts_boutiques_montant"]),
                "transferts_inter_usines_sacs": str(v["transferts_inter_usines_sacs"]),
                "transferts_inter_usines_montant": str(v["transferts_inter_usines_montant"]),
                "total_transferts_montant": str(total_transferts),
            })
        return Response(result)


class DetailBoutiqueView(APIView):
    """
    GET /api/comptable/rapport-boutiques/<lieu_id>/
    Détail d'une boutique : tickets + cessions reçues, avec filtres date.
    Restriction : la boutique doit appartenir à l'entreprise du comptable (anti-IDOR).
    Performance : totaux calculés via agrégation SQL.
    """
    permission_classes = [IsComptableRole]

    def get(self, request, lieu_id):
        from api.serializers import TransfertCessionSerializer
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")

        try:
            lieu = Lieu.objects.get(
                pk=lieu_id,
                type_lieu=Lieu.TYPE_MAGASIN,
                entreprise=request.user.entreprise,  # anti-IDOR
            )
        except Lieu.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=404)

        tickets_qs = Ticket.objects.filter(lieu=lieu).prefetch_related("lignes__produit").order_by("-date")
        if debut:
            tickets_qs = tickets_qs.filter(date__date__gte=debut)
        if fin:
            tickets_qs = tickets_qs.filter(date__date__lte=fin)

        cessions_qs = TransfertCession.objects.filter(boutique=lieu).select_related(
            "lot__lieu_usine", "lot__produit_fini"
        ).order_by("-created_at")
        if debut:
            cessions_qs = cessions_qs.filter(created_at__date__gte=debut)
        if fin:
            cessions_qs = cessions_qs.filter(created_at__date__lte=fin)

        # Totaux via agrégation SQL (une query au lieu de N itérations Python)
        lignes_qs = LigneVente.objects.filter(ticket__lieu=lieu)
        if debut:
            lignes_qs = lignes_qs.filter(ticket__date__date__gte=debut)
        if fin:
            lignes_qs = lignes_qs.filter(ticket__date__date__lte=fin)
        total_lignes = lignes_qs.aggregate(total=Sum(_VENTE_MONTANT))["total"] or Decimal("0")

        # Mouture : s'ajoute au total ventes (coût de service écrasement)
        tickets_mouture_qs = Ticket.objects.filter(lieu=lieu, mouture=True)
        if debut:
            tickets_mouture_qs = tickets_mouture_qs.filter(date__date__gte=debut)
        if fin:
            tickets_mouture_qs = tickets_mouture_qs.filter(date__date__lte=fin)
        total_mouture = tickets_mouture_qs.aggregate(total=Sum("cout_mouture"))["total"] or Decimal("0")
        total_ventes = total_lignes + total_mouture

        total_cessions = cessions_qs.aggregate(total=Sum(_CESSION_MONTANT))["total"] or Decimal("0")

        from api.serializers import TicketSerializer
        return Response({
            "lieu_id": lieu.id,
            "lieu_nom": lieu.nom,
            "total_ventes_produits": str(total_lignes),
            "total_mouture": str(total_mouture),
            "total_ventes": str(total_ventes),
            "total_cessions_recues": str(total_cessions),
            "tickets": TicketSerializer(tickets_qs, many=True).data,
            "cessions_recues": TransfertCessionSerializer(cessions_qs, many=True).data,
        })


class DetailUsineView(APIView):
    """
    GET /api/comptable/rapport-usines/<lieu_id>/
    Détail d'une usine : achats + cessions envoyées + transferts inter-usines.
    Restriction : l'usine doit appartenir à l'entreprise du comptable (anti-IDOR).
    Performance : totaux calculés via agrégation SQL.
    """
    permission_classes = [IsComptableRole]

    def get(self, request, lieu_id):
        from api.serializers import (
            AchatUsineSerializer,
            TransfertCessionSerializer,
            TransfertInterUsineSerializer,
        )
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")

        try:
            lieu = Lieu.objects.get(
                pk=lieu_id,
                type_lieu=Lieu.TYPE_USINE,
                entreprise=request.user.entreprise,  # anti-IDOR
            )
        except Lieu.DoesNotExist:
            return Response({"detail": "Usine introuvable."}, status=404)

        achats_qs = AchatUsine.objects.filter(lieu=lieu).select_related("created_by").order_by("-date")
        if debut:
            achats_qs = achats_qs.filter(date__date__gte=debut)
        if fin:
            achats_qs = achats_qs.filter(date__date__lte=fin)

        cessions_qs = TransfertCession.objects.filter(lot__lieu_usine=lieu).select_related(
            "boutique", "lot__produit_fini"
        ).order_by("-created_at")
        if debut:
            cessions_qs = cessions_qs.filter(created_at__date__gte=debut)
        if fin:
            cessions_qs = cessions_qs.filter(created_at__date__lte=fin)

        inter_sortants_qs = TransfertInterUsine.objects.filter(lot__lieu_usine=lieu).select_related(
            "usine_destination", "lot__produit_fini"
        ).order_by("-created_at")
        if debut:
            inter_sortants_qs = inter_sortants_qs.filter(created_at__date__gte=debut)
        if fin:
            inter_sortants_qs = inter_sortants_qs.filter(created_at__date__lte=fin)

        inter_entrants_qs = TransfertInterUsine.objects.filter(usine_destination=lieu).select_related(
            "lot__lieu_usine", "lot__produit_fini"
        ).order_by("-created_at")
        if debut:
            inter_entrants_qs = inter_entrants_qs.filter(created_at__date__gte=debut)
        if fin:
            inter_entrants_qs = inter_entrants_qs.filter(created_at__date__lte=fin)

        # Totaux via agrégation SQL
        total_achats = achats_qs.aggregate(total=Sum("prix_total"))["total"] or Decimal("0")
        total_cessions = cessions_qs.aggregate(total=Sum(_CESSION_MONTANT))["total"] or Decimal("0")
        total_inter_sortants = inter_sortants_qs.aggregate(total=Sum(_CESSION_MONTANT))["total"] or Decimal("0")

        return Response({
            "lieu_id": lieu.id,
            "lieu_nom": lieu.nom,
            "total_achats": str(total_achats),
            "total_transferts_boutiques": str(total_cessions),
            "total_transferts_inter_usines_sortants": str(total_inter_sortants),
            "total_transferts": str(total_cessions + total_inter_sortants),
            "achats": AchatUsineSerializer(achats_qs, many=True).data,
            "cessions_vers_boutiques": TransfertCessionSerializer(cessions_qs, many=True).data,
            "transferts_inter_usines_sortants": TransfertInterUsineSerializer(inter_sortants_qs, many=True).data,
            "transferts_inter_usines_entrants": TransfertInterUsineSerializer(inter_entrants_qs, many=True).data,
        })


class BilanView(APIView):
    """
    GET /api/comptable/bilan/
    Bilan financier global : revenus (ventes) vs charges (achats matières + dépenses).
    Filtres : ?debut=YYYY-MM-DD&fin=YYYY-MM-DD
    Accessible au comptable et à l'admin (IsComptableRole).
    Restreint à l'entreprise de l'utilisateur connecté.
    Performance : agrégations SQL au lieu de boucles Python.
    """
    permission_classes = [IsComptableRole]

    def get(self, request):
        entreprise = request.user.entreprise
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")

        # Revenus : agrégation SQL sur les lignes de vente (entreprise uniquement)
        lignes_qs = LigneVente.objects.filter(ticket__lieu__entreprise=entreprise)
        if debut:
            lignes_qs = lignes_qs.filter(ticket__date__date__gte=debut)
        if fin:
            lignes_qs = lignes_qs.filter(ticket__date__date__lte=fin)
        total_lignes = lignes_qs.aggregate(total=Sum(_VENTE_MONTANT))["total"] or Decimal("0")

        # Coût mouture : s'ajoute au total ventes
        tickets_mouture_qs = Ticket.objects.filter(
            lieu__entreprise=entreprise, mouture=True
        )
        if debut:
            tickets_mouture_qs = tickets_mouture_qs.filter(date__date__gte=debut)
        if fin:
            tickets_mouture_qs = tickets_mouture_qs.filter(date__date__lte=fin)
        total_mouture = tickets_mouture_qs.aggregate(total=Sum("cout_mouture"))["total"] or Decimal("0")
        total_ventes = total_lignes + total_mouture

        # Coûts matières : agrégation SQL sur les achats usine (entreprise uniquement)
        achats_qs = AchatUsine.objects.filter(lieu__entreprise=entreprise)
        if debut:
            achats_qs = achats_qs.filter(date__date__gte=debut)
        if fin:
            achats_qs = achats_qs.filter(date__date__lte=fin)
        total_achats = achats_qs.aggregate(total=Sum("prix_total"))["total"] or Decimal("0")

        # Charges opérationnelles : agrégation SQL sur les dépenses (entreprise uniquement)
        depenses_qs = Depense.objects.filter(lieu__entreprise=entreprise)
        if debut:
            depenses_qs = depenses_qs.filter(date__date__gte=debut)
        if fin:
            depenses_qs = depenses_qs.filter(date__date__lte=fin)
        total_depenses = depenses_qs.aggregate(total=Sum("montant"))["total"] or Decimal("0")

        total_charges = total_achats + total_depenses
        benefice_net = total_ventes - total_charges

        return Response({
            "total_ventes_produits": str(total_lignes),
            "total_mouture": str(total_mouture),
            "total_ventes": str(total_ventes),
            "total_achats_matieres": str(total_achats),
            "total_depenses_operationnelles": str(total_depenses),
            "total_charges": str(total_charges),
            "benefice_net": str(benefice_net),
            "est_benefice": benefice_net >= Decimal("0"),
        })
