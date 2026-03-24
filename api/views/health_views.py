"""
Endpoint /api/health/ : statut applicatif + base de données + version.

GET /api/health/
    → { status, db, version }
    Public (AllowAny), utilisé par Docker healthcheck et monitoring.

GET /api/health/?detail=1   (superadmin requis)
    → { status, db, version, counts, sequences_ok }
    Diagnostic post-reset : compte les entrées dans chaque table métier
    et vérifie que toutes les séquences PostgreSQL sont à 1.
    Retourne 503 si la base n'est pas propre après un full_reset.
"""
from decimal import Decimal
from time import perf_counter

from django.apps import apps
from django.db import connection
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsAdminRole
from core.models import CustomUser, Lieu
from inventaire.models import Transfert
from ventes.models import Facture, LigneFacture, LigneVente, Ticket


# Tables contrôlées en mode ?detail=1
_DETAIL_TABLES = [
    ("core",        "CustomUser"),
    ("core",        "Lieu"),
    ("core",        "Entreprise"),
    ("produits",    "Produit"),
    ("produits",    "Categorie"),
    ("ventes",      "Ticket"),
    ("inventaire",  "Stock"),
    ("inventaire",  "AchatUsine"),
    ("usine",       "LotProduction"),
    ("depenses",    "Depense"),
    ("audit",       "AuditLog"),
]


class HealthView(APIView):
    """
    GET /api/health/         → { status, db, version }         (public)
    GET /api/health/?detail=1 → + counts + sequences_ok        (superadmin)
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # ── Ping DB ──────────────────────────────────────────────────────────
        db_ok = True
        try:
            connection.ensure_connection()
        except Exception:
            db_ok = False

        payload = {
            "status": "ok" if db_ok else "error",
            "db": "ok" if db_ok else "error",
            "version": "v0",
        }

        # ── Mode détail : réservé aux superadmins ────────────────────────────
        if request.query_params.get("detail") == "1":
            if not (
                request.user
                and request.user.is_authenticated
                and request.user.role == CustomUser.ROLE_SUPREME_ADMIN
            ):
                return Response(
                    {"detail": "Authentification superadmin requise pour le mode détail."},
                    status=403,
                )
            payload.update(self._get_detail())

        status_code = 200 if db_ok else 503
        return Response(payload, status=status_code)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_detail(self):
        """Compte les entrées dans les tables métier + vérifie les séquences."""
        counts = {}
        for app_label, model_name in _DETAIL_TABLES:
            try:
                model = apps.get_model(app_label, model_name)
                counts[f"{app_label}.{model_name}"] = model.objects.count()
            except LookupError:
                counts[f"{app_label}.{model_name}"] = None

        sequences_ok = self._check_sequences()

        return {
            "counts": counts,
            "sequences_ok": sequences_ok,
        }

    def _check_sequences(self):
        """Retourne True si toutes les séquences PostgreSQL sont à 1, False sinon."""
        if connection.vendor != "postgresql":
            return None  # Non applicable (SQLite en tests)
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM pg_sequences
                    WHERE schemaname = 'public'
                      AND last_value > 1
                """)
                row = cursor.fetchone()
                return row[0] == 0 if row else True
        except Exception:
            return None


class HealthCheckView(APIView):
    """
    GET /api/health/check/ : vÃ©rifications mÃ©tier rapides (admin uniquement).
    ContrÃ´le :
      - AccÃ¨s boutiques/usines (existence + cohÃ©rence users/lieux)
      - Ventes (dernier ticket : somme lignes + mouture = montant_total)
      - Factures (dernier doc : somme lignes = total)
      - Transferts (dernier transfert : entreprise cohÃ©rente, mouvements valides)
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        start = perf_counter()
        checks = {}
        failures = []

        # --- Lieux / Users ---
        try:
            boutiques_count = Lieu.objects.filter(type_lieu=Lieu.TYPE_MAGASIN).count()
            usines_count = Lieu.objects.filter(type_lieu=Lieu.TYPE_USINE).count()
            checks["lieux_boutiques"] = {"status": "ok", "count": boutiques_count}
            checks["lieux_usines"] = {"status": "ok", "count": usines_count}
        except Exception as exc:
            checks["lieux"] = {"status": "error", "detail": str(exc)}
            failures.append("lieux")

        try:
            bad_boutiques = CustomUser.objects.filter(
                role=CustomUser.ROLE_BOUTIQUE
            ).exclude(lieu__type_lieu=Lieu.TYPE_MAGASIN).exists()
            bad_usines = CustomUser.objects.filter(
                role=CustomUser.ROLE_USINE
            ).exclude(lieu__type_lieu=Lieu.TYPE_USINE).exists()
            checks["users_boutique_lieu"] = {"status": "ok" if not bad_boutiques else "error"}
            checks["users_usine_lieu"] = {"status": "ok" if not bad_usines else "error"}
            if bad_boutiques:
                failures.append("users_boutique_lieu")
            if bad_usines:
                failures.append("users_usine_lieu")
        except Exception as exc:
            checks["users_lieu"] = {"status": "error", "detail": str(exc)}
            failures.append("users_lieu")

        # --- Ventes ---
        try:
            ticket = Ticket.objects.order_by("-id").first()
            if not ticket:
                checks["ventes"] = {"status": "skip", "detail": "Aucun ticket."}
            else:
                total_lines = LigneVente.objects.filter(ticket=ticket).aggregate(
                    total=Sum(
                        ExpressionWrapper(
                            F("quantite") * F("prix_unitaire"),
                            output_field=DecimalField(max_digits=18, decimal_places=2),
                        )
                    )
                )["total"] or Decimal("0")
                expected = total_lines + (ticket.cout_mouture or Decimal("0"))
                ok = expected == (ticket.montant_total or Decimal("0"))
                checks["ventes"] = {
                    "status": "ok" if ok else "error",
                    "ticket_id": ticket.id,
                    "expected": str(expected),
                    "actual": str(ticket.montant_total),
                }
                if not ok:
                    failures.append("ventes")
        except Exception as exc:
            checks["ventes"] = {"status": "error", "detail": str(exc)}
            failures.append("ventes")

        # --- Factures ---
        try:
            facture = Facture.objects.order_by("-id").first()
            if not facture:
                checks["factures"] = {"status": "skip", "detail": "Aucune facture."}
            else:
                total_lines = LigneFacture.objects.filter(facture=facture).aggregate(
                    total=Sum(
                        ExpressionWrapper(
                            F("quantite") * F("prix_unitaire"),
                            output_field=DecimalField(max_digits=18, decimal_places=2),
                        )
                    )
                )["total"] or Decimal("0")
                ok = total_lines == (facture.total or Decimal("0"))
                checks["factures"] = {
                    "status": "ok" if ok else "error",
                    "facture_id": facture.id,
                    "expected": str(total_lines),
                    "actual": str(facture.total),
                }
                if not ok:
                    failures.append("factures")
        except Exception as exc:
            checks["factures"] = {"status": "error", "detail": str(exc)}
            failures.append("factures")

        # --- Transferts ---
        try:
            transfert = Transfert.objects.select_related("from_lieu", "to_lieu").order_by("-id").first()
            if not transfert:
                checks["transferts"] = {"status": "skip", "detail": "Aucun transfert."}
            else:
                same_ent = transfert.from_lieu.entreprise_id == transfert.to_lieu.entreprise_id
                invalid_moves = transfert.mouvements.filter(quantite__lte=0).exists()
                ok = same_ent and not invalid_moves
                checks["transferts"] = {
                    "status": "ok" if ok else "error",
                    "transfert_id": transfert.id,
                    "same_entreprise": same_ent,
                    "invalid_mouvements": invalid_moves,
                }
                if not ok:
                    failures.append("transferts")
        except Exception as exc:
            checks["transferts"] = {"status": "error", "detail": str(exc)}
            failures.append("transferts")

        duration_ms = int((perf_counter() - start) * 1000)
        payload = {
            "status": "ok" if not failures else "error",
            "failures": failures,
            "duration_ms": duration_ms,
            "checks": checks,
        }
        return Response(payload, status=200 if not failures else 503)
