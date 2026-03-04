"""
Middleware sécurité KONIS : en-têtes de protection web et corrélation des logs.

SecurityHeadersMiddleware :
  - Headers anti-clickjacking, MIME-sniffing, XSS, CSP, Permissions-Policy
  - Cache-Control: no-store sur toutes les routes /api/ (sauf /api/health/)
    → empêche le navigateur et tout proxy intermédiaire de mettre en cache
      des données financières ou personnelles. Résout l'affichage de compteurs
      résiduels après un full_reset.

RequestIDMiddleware :
  - Génère un identifiant unique (UUID4) pour chaque requête HTTP
  - Exposé en tant que X-Request-ID dans la réponse pour corrélation des logs
  - Lit X-Request-ID de la requête entrante si présent (load balancer / nginx)
"""
import uuid

from django.utils.deprecation import MiddlewareMixin

# Routes API : on force no-store sauf le health check public.
_API_PREFIX = "/api/"
_HEALTH_PATH = "/api/health/"


class RequestIDMiddleware(MiddlewareMixin):
    """
    Attache un identifiant unique à chaque requête pour la corrélation des logs.

    Comportement :
      - Si la requête entrante contient déjà X-Request-ID (ex. nginx, load balancer),
        ce header est réutilisé tel quel.
      - Sinon, un UUID4 est généré.
      - L'ID est accessible via request.request_id dans les vues/middleware suivants.
      - L'ID est renvoyé dans le header X-Request-ID de la réponse.

    Usage dans les logs :
        import logging
        logger = logging.getLogger(__name__)
        # Dans une vue :
        logger.warning("Erreur", extra={"request_id": request.request_id})
    """

    def process_request(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.META["X_REQUEST_ID"] = request_id
        request.request_id = request_id

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", None)
        if request_id:
            response["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Ajoute les en-têtes de sécurité HTTP sur chaque réponse :
    - X-Frame-Options            : anti clickjacking
    - X-Content-Type-Options     : anti MIME sniffing
    - Referrer-Policy            : fuite URL réduite
    - Content-Security-Policy    : politique basique V0
    - X-XSS-Protection           : protection XSS legacy
    - Permissions-Policy         : désactive caméra/micro/géolocalisation
    - Cache-Control / Pragma     : no-store sur toutes les routes /api/ (sauf health)
    """

    def process_response(self, request, response):
        # ── Headers communs à toutes les réponses ────────────────────────────
        if "X-Frame-Options" not in response:
            response["X-Frame-Options"] = "DENY"
        if "X-Content-Type-Options" not in response:
            response["X-Content-Type-Options"] = "nosniff"
        if "Referrer-Policy" not in response:
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'"
            )
        if "X-XSS-Protection" not in response:
            response["X-XSS-Protection"] = "1; mode=block"
        if "Permissions-Policy" not in response:
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # ── Cache-Control : no-store pour toutes les routes API protégées ────
        # Raison : les données financières (ventes, stocks, bilan) ne doivent
        # jamais être servies depuis un cache navigateur ou proxy après un
        # full_reset. Sans ce header, le navigateur peut afficher des compteurs
        # issus d'une réponse mise en cache avant le reset.
        path = getattr(request, "path", "")
        if path.startswith(_API_PREFIX) and path != _HEALTH_PATH:
            if "Cache-Control" not in response:
                response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"

        return response
