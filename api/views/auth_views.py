"""
API Auth : login (JWT en cookie httpOnly), refresh avec rotation, logout avec blacklist.
"""
import hmac
import json
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.serializers import UserMinimalSerializer
from api.throttling import LoginIPRateThrottle, LoginRateThrottle, RefreshRateThrottle
from audit.services import audit_log
from core.models import CustomUser, Entreprise


def _get_request_data(request):
    """Extraire les donnees de la requete, supporte DRF Request et WSGIRequest."""
    if hasattr(request, 'data'):
        return request.data
    if hasattr(request, 'body') and request.body:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return request.POST if hasattr(request, 'POST') else {}


def _serialize_user(user: CustomUser) -> dict:
    data = UserMinimalSerializer(user).data
    data["is_factory"] = user.is_factory()
    data["role_normalized"] = "factory" if user.is_factory() else data.get("role")
    return data


def _ensure_user_entreprise(user: CustomUser) -> Entreprise:
    """
    Assure qu'un utilisateur est rattaché à une entreprise existante.
    Si aucune entreprise n'existe encore, en crée une par défaut.
    """
    if getattr(settings, "SINGLE_ENTREPRISE", False):
        entreprise = Entreprise.get_primary()
        if user.entreprise_id != entreprise.id:
            user.entreprise = entreprise
            user.save(update_fields=["entreprise"])
        return entreprise
    if user.entreprise_id:
        return user.entreprise
    entreprise = Entreprise.get_primary()
    user.entreprise = entreprise
    user.save(update_fields=["entreprise"])
    return entreprise


def _set_jwt_cookies(response, access_token, refresh_token=None):
    """Définit les cookies httpOnly pour JWT."""
    from datetime import timedelta
    cookie_opts = {
        "httponly": True,
        "samesite": "Strict",  # Strict : protège contre le CSRF cross-site
        "secure": not getattr(settings, "DEBUG", True),
    }
    access_name = getattr(settings, "SIMPLE_JWT_COOKIE_ACCESS_NAME", "access_token")
    refresh_name = getattr(settings, "SIMPLE_JWT_COOKIE_REFRESH_NAME", "refresh_token")
    jwt_cfg = getattr(settings, "SIMPLE_JWT", {})
    access_lt = jwt_cfg.get("ACCESS_TOKEN_LIFETIME", timedelta(hours=5))
    refresh_lt = jwt_cfg.get("REFRESH_TOKEN_LIFETIME", timedelta(days=7))
    max_age_access = int(access_lt.total_seconds()) if hasattr(access_lt, "total_seconds") else 3600 * 5
    max_age_refresh = int(refresh_lt.total_seconds()) if hasattr(refresh_lt, "total_seconds") else 3600 * 24 * 7

    response.set_cookie(access_name, str(access_token), max_age=max_age_access, **cookie_opts)
    if refresh_token:
        response.set_cookie(refresh_name, str(refresh_token), max_age=max_age_refresh, **cookie_opts)
    return response


def _clear_jwt_cookies(response):
    """Supprime les cookies JWT."""
    access_name = getattr(settings, "SIMPLE_JWT_COOKIE_ACCESS_NAME", "access_token")
    refresh_name = getattr(settings, "SIMPLE_JWT_COOKIE_REFRESH_NAME", "refresh_token")
    for name in (access_name, refresh_name):
        response.delete_cookie(name, samesite="Strict")
    return response


class LoginView(APIView):
    """POST /api/auth/login/ : credentials -> JWT dans cookies + user."""
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, LoginIPRateThrottle]

    def post(self, request, *args, **kwargs):
        from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
        
        # Obtenir les donnees de la requete (supporte WSGIRequest et DRF Request)
        data = _get_request_data(request)
        
        # Compat: autoriser login par email en plus du username.
        raw_username = data.get("username")
        password = data.get("password")
        if raw_username and "@" in str(raw_username):
            matched = CustomUser.objects.filter(email__iexact=str(raw_username).strip()).first()
            if matched:
                data = data.copy() if hasattr(data, 'copy') else dict(data)
                data["username"] = matched.username
        elif not raw_username and data.get("email"):
            matched = CustomUser.objects.filter(email__iexact=str(data.get("email")).strip()).first()
            if matched and password:
                data = data.copy() if hasattr(data, 'copy') else dict(data)
                data["username"] = matched.username

        # Utiliser le serializer directement
        serializer = TokenObtainPairSerializer(data=data)
        try:
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        access = serializer.validated_data["access"]
        refresh = serializer.validated_data["refresh"]
        user_id = AccessToken(access).get("user_id")
        user = CustomUser.objects.get(pk=user_id)
        _ensure_user_entreprise(user)
        
        response = Response({
            "user": _serialize_user(user),
            "is_factory": user.is_factory(),
            "role": "factory" if user.is_factory() else user.role,
        })
        
        _set_jwt_cookies(response, access, refresh)
        audit_log(user=user, action="connexion", object_type="user", object_id=user.pk, request=request)
        
        # Si appel depuis Next.js SSR (proxy interne), inclure les tokens pour que Next les place en cookies.
        # Authentifié par secret partagé INTERNAL_API_SECRET — jamais une valeur hardcodée.
        _secret = getattr(settings, "INTERNAL_API_SECRET", "")
        _proxy = request.headers.get("X-Proxy", "")
        if _secret and _proxy and hmac.compare_digest(_proxy, _secret):
            response.data["access"] = str(access)
            response.data["refresh"] = str(refresh)
        return response


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh/ : refresh token (cookie) -> nouveau access en cookie."""
    permission_classes = [AllowAny]
    throttle_classes = [RefreshRateThrottle]  # 10/min par IP, toujours appliqué (pas d'exemption auth)

    def post(self, request, *args, **kwargs):
        refresh_name = getattr(settings, "SIMPLE_JWT_COOKIE_REFRESH_NAME", "refresh_token")
        token = request.COOKIES.get(refresh_name)
        if not token:
            data = _get_request_data(request)
            token = data.get("refresh")
        if not token:
            return Response(
                {"detail": "Refresh token manquant (cookie ou body)."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        from rest_framework_simplejwt.serializers import TokenRefreshSerializer
        ser = TokenRefreshSerializer(data={"refresh": str(token)})
        try:
            if not ser.is_valid():
                return Response(ser.errors, status=status.HTTP_401_UNAUTHORIZED)
        except TokenError:
            return Response(
                {"detail": "Refresh token invalide ou expiré."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        access = ser.validated_data["access"]
        new_refresh = ser.validated_data.get("refresh")
        response_payload = {
            "access": str(access),
            "refresh": str(new_refresh or token),
        }
        response = Response(response_payload)
        _set_jwt_cookies(response, access, new_refresh)
        return response


class LogoutView(APIView):
    """POST /api/auth/logout/ : blacklist du refresh token puis suppression des cookies JWT."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_name = getattr(settings, "SIMPLE_JWT_COOKIE_REFRESH_NAME", "refresh_token")
        token = request.COOKIES.get(refresh_name)
        if not token:
            data = _get_request_data(request)
            token = data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception:
                pass  # Token invalide ou déjà blacklisté : on supprime les cookies quand même
        response = Response({"ok": True})
        _clear_jwt_cookies(response)
        return response


class MeView(APIView):
    """GET /api/auth/me/ : utilisateur connecté."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _ensure_user_entreprise(request.user)
        return Response(_serialize_user(request.user))
