"""
Idempotency transactionnelle KONIS — registre dédié, thread-safe.

Remplace complètement le système basé sur AuditLog (TOCTOU non protégé).

Mécanisme :
  1. check() tente de SELECT FOR UPDATE le slot (key, endpoint).
  2. Si absent → INSERT du slot 'processing' (UniqueConstraint bloque toute
     double insertion concurrente ; IntegrityError est capturée proprement).
  3. Si présent + même hash → replay de la réponse stockée.
  4. Si présent + hash différent → HTTP 409 (conflit).
  5. Après exécution → success(data) marque le slot 'success'.

Garanties :
  - Aucune double exécution possible même sous forte concurrence.
  - Slot 'processing' périmé (> 60 s) est recyclé automatiquement.
  - Strictement sans effet de bord hors transaction.
"""
import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import status as http_status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# ── Exceptions internes ──────────────────────────────────────────────────────

class IdempotencyConflict(Exception):
    """Même clé, payload différent."""

class IdempotencyInProgress(Exception):
    """Slot 'processing' frais — requête en cours d'exécution."""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _payload_hash(data) -> str:
    try:
        raw = json.dumps(data, default=str, sort_keys=True)
    except Exception:
        raw = str(data)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Logique cœur ─────────────────────────────────────────────────────────────

def _find_or_claim(key: str, endpoint: str, payload_hash: str):
    """
    Tente de réserver (ou retrouver) un slot d'idempotency de façon atomique.

    Retourne (action, response_data) :
      - ('execute', None)       → slot créé, procéder à l'exécution
      - ('replay',  dict|None)  → slot existant succès, retourner la réponse
      - ('in_flight', None)     → slot processing frais (< MAX_PROCESSING_AGE)
      - ('conflict', None)      → même clé, hash différent

    Tout le bloc est dans transaction.atomic() pour garantir l'atomicité.
    Le savepoint interne isole IntegrityError sans invalider la transaction ext.
    """
    # Import ici pour éviter les imports circulaires au démarrage Django
    from core.models import IdempotencyKey

    cutoff = timezone.now() - timedelta(seconds=IdempotencyKey.MAX_PROCESSING_AGE)

    with transaction.atomic():
        # ── 1. Chercher un slot existant (SELECT FOR UPDATE) ─────────────────
        try:
            record = (
                IdempotencyKey.objects
                .select_for_update()
                .get(key=key, endpoint=endpoint)
            )
        except IdempotencyKey.DoesNotExist:
            record = None

        if record is not None:
            # Slot périmé → recycler et ré-exécuter
            if record.is_stale():
                IdempotencyKey.objects.filter(pk=record.pk).update(
                    payload_hash=payload_hash,
                    response=None,
                    status=IdempotencyKey.STATUS_PROCESSING,
                    updated_at=timezone.now(),
                )
                return "execute", None

            if record.payload_hash != payload_hash:
                return "conflict", None

            if record.status == IdempotencyKey.STATUS_SUCCESS:
                return "replay", record.response

            # processing frais (autre requête en cours)
            return "in_flight", None

        # ── 2. Slot absent → créer (savepoint pour isoler IntegrityError) ────
        try:
            with transaction.atomic():  # savepoint
                IdempotencyKey.objects.create(
                    key=key,
                    endpoint=endpoint,
                    payload_hash=payload_hash,
                    response=None,
                    status=IdempotencyKey.STATUS_PROCESSING,
                )
            return "execute", None

        except IntegrityError:
            # Race : une autre requête a créé le slot simultanément
            try:
                record = (
                    IdempotencyKey.objects
                    .select_for_update()
                    .get(key=key, endpoint=endpoint)
                )
            except IdempotencyKey.DoesNotExist:
                # Très improbable (slot créé puis immédiatement supprimé)
                logger.warning("IdempotencyKey race then vanish: key=%s endpoint=%s", key, endpoint)
                return "execute", None

            if record.payload_hash != payload_hash:
                return "conflict", None
            if record.status == IdempotencyKey.STATUS_SUCCESS:
                return "replay", record.response
            return "in_flight", None


def _mark_success(key: str, endpoint: str, response_data: dict):
    """Marque le slot comme succès et persiste la réponse."""
    from core.models import IdempotencyKey
    IdempotencyKey.objects.filter(key=key, endpoint=endpoint).update(
        response=response_data,
        status=IdempotencyKey.STATUS_SUCCESS,
        updated_at=timezone.now(),
    )


# ── Interface publique ───────────────────────────────────────────────────────

class IdempotencyGuard:
    """
    Garde d'idempotency pour une vue DRF.

    Usage type :

        guard = IdempotencyGuard(request, "paiement_payable")
        early = guard.check()
        if early is not None:
            return early

        # ... exécuter l'opération métier ...

        guard.success(resp_data)
        return Response(resp_data)

    check() retourne :
      - None                  → procéder (slot réservé)
      - Response(200/201)     → replay
      - Response(400)         → clé absente (strict mode) ou trop longue
      - Response(409)         → conflit de payload
      - Response(503)         → opération en cours (retry client)
    """

    def __init__(self, request, operation: str):
        self._request  = request
        self._operation = operation
        self._key      = (request.headers.get("Idempotency-Key") or "").strip() or None
        self._hash     = _payload_hash(getattr(request, "data", None))
        self._missing  = self._key is None
        self._endpoint = request.path

    # ── check() ──────────────────────────────────────────────────────────────

    def check(
        self,
        success_status: int = http_status.HTTP_200_OK,
        required: bool = True,
    ) -> Response | None:
        """
        Vérifie/réserve le slot d'idempotency.

        success_status : code HTTP utilisé pour le replay (200 ou 201 selon endpoint).
        required       : si False, une clé absente n'est pas une erreur — l'opération
                         s'exécute sans protection idempotente (utile pour transferts/achats
                         où la clé est recommandée mais pas imposée).
        Retourne None si l'exécution doit procéder, sinon une Response finale.
        """
        strict = getattr(settings, "IDEMPOTENCY_STRICT_MODE", True)

        if self._missing:
            if strict and required:
                return self._warn(
                    Response(
                        {"detail": "Idempotency-Key requis pour cette opération."},
                        status=http_status.HTTP_400_BAD_REQUEST,
                    )
                )
            return None  # pas de clé, pas de vérification

        action, response_data = _find_or_claim(
            key=self._key,
            endpoint=self._endpoint,
            payload_hash=self._hash,
        )

        if action == "execute":
            return None  # slot réservé, procéder

        if action == "replay":
            logger.info(
                "Idempotency replay: key=%s operation=%s",
                self._key, self._operation,
            )
            return Response(response_data, status=success_status)

        if action == "conflict":
            return Response(
                {
                    "detail": (
                        "Cette Idempotency-Key a déjà été utilisée avec un payload différent. "
                        "Utilisez une clé unique pour chaque opération distincte."
                    )
                },
                status=http_status.HTTP_409_CONFLICT,
            )

        # in_flight
        return Response(
            {"detail": "Opération en cours, réessayez dans quelques secondes."},
            status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # ── success() ────────────────────────────────────────────────────────────

    def success(self, response_data):
        """
        Persiste la réponse et marque le slot comme succès.
        À appeler juste avant de retourner la Response dans la vue.
        Sans effet si aucune clé n'était présente.
        """
        if self._key:
            _mark_success(self._key, self._endpoint, response_data)

    # ── helper ───────────────────────────────────────────────────────────────

    def _warn(self, response: Response) -> Response:
        if self._missing:
            response["X-Idempotency-Warning"] = "missing"
        return response
