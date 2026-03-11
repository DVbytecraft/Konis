"""
Settings production KONIS – PostgreSQL (DATABASE_URL), DEBUG False, sécurité HTTPS.
"""
import os

import dj_database_url
import sentry_sdk

from .base import *  # noqa: F401, F403

DEBUG = False
ALLOWED_HOSTS = [
    x.strip()
    for x in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if x.strip()
]
if not ALLOWED_HOSTS:
    raise ValueError("DJANGO_ALLOWED_HOSTS doit être défini en production (ex: konis-api.onrender.com)")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY doit être défini en production")

# Base de données : DATABASE_URL (Render PostgreSQL) ou variables POSTGRES_*
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "konis"),
            "USER": os.environ.get("POSTGRES_USER", "konis"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
        }
    }

# CORS : origines autorisées (frontend DigitalOcean / domaine custom)
CORS_ALLOWED_ORIGINS = [
    x.strip()
    for x in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if x.strip()
]

# CSRF_TRUSTED_ORIGINS : obligatoire depuis Django 4.0 derrière tout proxy HTTPS.
# DigitalOcean App Platform fait passer les requêtes via son load balancer —
# sans cette variable, Django renvoie 403 sur l'admin et les formulaires CSRF.
CSRF_TRUSTED_ORIGINS = [
    x.strip()
    for x in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if x.strip()
]

# Sécurité HTTPS
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# ⚠️ SECURE_HSTS_PRELOAD délibérément absent — quasi-irréversible.
# Activer uniquement après soumission intentionnelle à hstspreload.org.

# Static files : WhiteNoise (après SecurityMiddleware)
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
MIDDLEWARE.insert(idx + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Cache Redis (partagé entre tous les workers Gunicorn) ─────────────────────
# Obligatoire pour que le rate limiting DRF fonctionne en multi-workers.
# Sans Redis, chaque worker a son propre cache mémoire → limits non respectées.
_redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": True,  # Dégrade gracieusement si Redis est indisponible
        },
        "KEY_PREFIX": "konis",
        "TIMEOUT": 300,  # 5 minutes par défaut
    }
}

# ── Sentry (monitoring erreurs production) ────────────────────────────────────
# Configurer SENTRY_DSN dans .env.prod pour activer.
# Laisser vide = désactivé (pas d'erreur au démarrage).
_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        # Capturer 5% des transactions pour le performance monitoring
        traces_sample_rate=0.05,
        # Capturer les profils sur 1% des transactions tracées
        profiles_sample_rate=0.01,
        # Pas d'envoi des données personnelles (RGPD)
        send_default_pii=False,
        environment="production",
        release=os.environ.get("APP_VERSION", "v1"),
    )

# ── Logging structuré JSON — ingestible par ELK/Datadog/Loki ─────────────────
# Chaque ligne = JSON valide avec levelname, timestamp, module, message, request_id
# Le request_id est injecté via RequestIDMiddleware.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            # Format JSON exploitable par tout aggregateur de logs
            "format": (
                '{{"level":"{levelname}",'
                '"time":"{asctime}",'
                '"logger":"{name}",'
                '"pid":{process},'
                '"msg":{message!r}}}'
            ),
            "style": "{",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",   # WARNING (pas ERROR) pour capturer les tentatives d'intrusion
            "propagate": False,
        },
        "konis": {
            # Logger applicatif KONIS — utilisez logging.getLogger("konis.xxx")
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
