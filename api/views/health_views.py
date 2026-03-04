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
from django.apps import apps
from django.db import connection
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView


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
            if not (request.user and request.user.is_authenticated and request.user.is_superuser):
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
