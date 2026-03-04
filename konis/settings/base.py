"""
Settings de base KONIS – communs à tous les environnements.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-fallback-change-in-prod")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # KONIS apps (ordre : core puis produits avant inventaire/ventes/depenses)
    "core",
    "audit",
    "produits",
    "usine",
    "inventaire",
    "ventes",
    "depenses",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "api.middleware.RequestIDMiddleware",          # Request ID en premier → disponible partout
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "api.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "konis.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "konis.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.CustomUser"

# DRF : JWT via cookie (prioritaire) ou Authorization + throttling
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.authentication.JWTCookieAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "600/hour",
        "login": "10/minute",
        "ventes_create": "60/minute",
        "mouture_create": "60/minute",
    },
    # Pagination par défaut : 50 items/page, paramètre ?page=N
    # Les vues qui veulent TOUT retourner doivent mettre pagination_class = None explicitement.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# JWT : expiration courte access (10 min), rotation refresh, blacklist au logout
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
SIMPLE_JWT_COOKIE_ACCESS_NAME = "access_token"
SIMPLE_JWT_COOKIE_REFRESH_NAME = "refresh_token"

# CORS : réglé finement en dev/prod
CORS_ALLOW_CREDENTIALS = True

# Sécurité navigateur : protection XSS activée
SECURE_BROWSER_XSS_FILTER = True

# CSRF : cookie lisible par JS (False = default Django) pour que le frontend puisse lire csrftoken
# et l'envoyer via X-CSRFToken header. SameSite=Strict protège déjà contre les attaques CSRF
# cross-site ; ceci est une défense en profondeur supplémentaire.
CSRF_COOKIE_HTTPONLY = False      # JS doit pouvoir lire le cookie csrftoken
CSRF_COOKIE_SAMESITE = "Strict"   # Protection CSRF par SameSite
SESSION_COOKIE_SAMESITE = "Strict"

# Secret partagé Next.js ↔ Django pour les appels SSR internes (header X-Proxy).
# Doit être identique dans INTERNAL_API_SECRET côté Next.js.
# Générer avec : python -c "import secrets; print(secrets.token_urlsafe(32))"
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")

# Hashers mots de passe (Django default = PBKDF2, sécurisé)
# Pas de modification nécessaire ; PASSWORD_HASHERS par défaut suffit.
