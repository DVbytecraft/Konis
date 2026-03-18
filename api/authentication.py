"""
Authentification JWT via cookies httpOnly.
Lit le token depuis le cookie ou l'en-tête Authorization.

Mécanisme de révocation globale (TokenRevocationEpoch) :
  Après un full_reset, tous les tokens émis avant le timestamp de révocation
  sont rejetés immédiatement, sans attendre leur expiration naturelle.
  Cela complète l'invalidation des OutstandingToken/BlacklistedToken en couvrant
  aussi les access tokens stateless (qui ne sont pas trackés dans la DB).

CSRF :
  Pour les requêtes authentifiées via cookie JWT, enforce_csrf() est appelé
  sur les méthodes mutantes (POST/PUT/PATCH/DELETE) en défense en profondeur.
  La protection principale reste SameSite=Strict sur les cookies JWT (nginx).
"""
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

# Middleware CSRF réutilisé pour enforce_csrf() (pattern issu de SessionAuthentication DRF)
_csrf_middleware = CsrfViewMiddleware(get_response=lambda req: None)

# Méthodes HTTP mutantes qui nécessitent une vérification CSRF
_CSRF_SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS", "TRACE"))


class JWTCookieAuthentication(JWTAuthentication):
    """
    Authentifie via JWT lu depuis le cookie (prioritaire) ou Authorization.

    Vérification supplémentaire : TokenRevocationEpoch.
    Si un full_reset a été exécuté, tout token émis avant le timestamp de
    révocation est rejeté avec une erreur claire, forçant le re-login.

    CSRF : pour les requêtes authentifiées par cookie (pas Authorization header),
    enforce_csrf() est appelé sur les méthodes mutantes.
    """

    def authenticate(self, request):
        cookie_name = getattr(settings, "SIMPLE_JWT_COOKIE_ACCESS_NAME", "access_token")
        raw_token = request.COOKIES.get(cookie_name)

        # Si pas de cookie JWT → déléguer à l'auth par header Authorization
        if not raw_token and request.META.get("HTTP_AUTHORIZATION"):
            return super().authenticate(request)
        if not raw_token:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
        except InvalidToken:
            return None

        # Enforce CSRF uniquement pour les requêtes authentifiées via cookie
        # (pas via Authorization header) et uniquement pour les méthodes mutantes.
        if request.method not in _CSRF_SAFE_METHODS:
            self._enforce_csrf(request)

        return user, validated_token

    def get_validated_token(self, raw_token):
        """
        Valide le token JWT puis vérifie l'époque de révocation globale.
        Lève InvalidToken si le token a été émis avant le dernier full_reset.
        """
        validated = super().get_validated_token(raw_token)
        self._check_revocation_epoch(validated)
        return validated

    def get_user(self, validated_token):
        """
        Récupère l'utilisateur et applique deux vérifications supplémentaires :
        1. is_active=False → rejet immédiat (désactivation effective sans attendre l'expiration)
        2. tokens_revoked_at → rejet si le token a été émis avant la révocation individuelle
           (changement de mot de passe, désactivation manuelle)
        """
        user = super().get_user(validated_token)
        if not user.is_active:
            raise InvalidToken("Compte désactivé. Contactez votre administrateur.")
        if user.tokens_revoked_at is not None:
            iat = validated_token.payload.get("iat")
            if iat is not None:
                token_issued_at = datetime.fromtimestamp(iat, tz=dt_timezone.utc)
                if token_issued_at <= user.tokens_revoked_at:
                    raise InvalidToken(
                        "Session révoquée suite à un changement de sécurité. "
                        "Veuillez vous reconnecter."
                    )
        return user

    # ── CSRF enforcement ──────────────────────────────────────────────────────

    def _enforce_csrf(self, request):
        """
        Vérifie le token CSRF pour les requêtes mutantes via cookie JWT.
        Lève PermissionDenied si le token CSRF est absent ou invalide.
        """
        check = _csrf_middleware.process_view(request, None, (), {})
        if check is not None:
            raise exceptions.PermissionDenied("CSRF token manquant ou invalide.")

    # ── Révocation globale post-full_reset ────────────────────────────────────

    def _check_revocation_epoch(self, token):
        """
        Vérifie que le token n'a pas été émis avant le dernier full_reset.

        Algorithme :
          1. Lit le dernier TokenRevocationEpoch (table vide = pas de révocation)
          2. Extrait le claim `iat` (issued-at) du payload JWT
          3. Si iat <= revoked_before → token révoqué → InvalidToken levée

        Performance : si la table est vide (cas normal en prod), la requête
        retourne None immédiatement. Aucun overhead en exploitation courante.
        """
        try:
            from core.models import TokenRevocationEpoch
        except ImportError:
            return  # Modèle pas encore migré → pas de vérification

        epoch = TokenRevocationEpoch.objects.order_by("-revoked_before").first()
        if epoch is None:
            return  # Aucun full_reset effectué → tous les tokens sont acceptés

        iat = token.payload.get("iat")
        if iat is None:
            return  # Pas de claim iat (ne devrait pas arriver avec simplejwt)

        token_issued_at = datetime.fromtimestamp(iat, tz=dt_timezone.utc)
        if token_issued_at <= epoch.revoked_before:
            raise InvalidToken(
                "Session expirée suite à une réinitialisation du système. "
                "Veuillez vous reconnecter."
            )
