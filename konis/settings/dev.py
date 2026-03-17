"""
Settings développement KONIS – PostgreSQL uniquement via DATABASE_URL.
En local : docker compose up -d démarre PostgreSQL, DATABASE_URL est injecté automatiquement.
Sans Docker : définir DATABASE_URL manuellement (voir .env.example).
SQLite n'est plus utilisé — même moteur en dev et en production.
"""
import os
from urllib.parse import urlparse

from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "backend", "0.0.0.0"]

_db_url = os.environ.get("DATABASE_URL", "")

if _db_url and _db_url.startswith("postgres"):
    _url = urlparse(_db_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _url.path[1:],
            "USER": _url.username,
            "PASSWORD": _url.password,
            "HOST": _url.hostname,
            "PORT": _url.port or 5432,
            "OPTIONS": {
                "client_encoding": "UTF8",
            },
            "CONN_MAX_AGE": 0,  # Pas de pool de connexion en dev (hot-reload friendly)
        }
    }
else:
    # Fallback SQLite — uniquement pour les outils hors-Docker (manage.py shell, IDE, CI sans DB)
    # En développement normal, lancer `docker compose up -d db` pour obtenir DATABASE_URL.
    import warnings
    warnings.warn(
        "DATABASE_URL absent ou invalide — SQLite utilisé en fallback. "
        "Lancez 'docker compose up -d db' pour utiliser PostgreSQL.",
        stacklevel=2,
    )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3004",
    "http://127.0.0.1:3004",
]

# SINGLE_ENTREPRISE : désactivé en dev/test (la migration 0005 crée une ENTREPRISE-DEFAULT
# qui décale les IDs et casse les filtres entreprise= dans les tests).
# La prod l'active via la variable d'environnement SINGLE_ENTREPRISE=1.
SINGLE_ENTREPRISE = os.environ.get("SINGLE_ENTREPRISE", "0").lower() in ("1", "true", "yes", "y")

# Secret partagé Next.js ↔ Django pour le proxy de login.
# Valeur par défaut en dev — DOIT correspondre à INTERNAL_API_SECRET dans frontend/.env.local.
# En production, remplacer par une valeur aléatoire forte (secrets.token_urlsafe(32)).
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "dev-konis-internal-secret")
