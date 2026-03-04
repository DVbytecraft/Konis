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

if not _db_url or not _db_url.startswith("postgres"):
    raise RuntimeError(
        "DATABASE_URL doit être défini et pointer vers PostgreSQL.\n"
        "Exemple : postgres://konis_user:konis_password@localhost:5433/konis_db\n"
        "Conseil  : lancez 'docker compose up -d db' puis exportez la variable,\n"
        "           ou copiez .env.example en .env et relancez avec django-environ."
    )

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

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Secret partagé Next.js ↔ Django pour le proxy de login.
# Valeur par défaut en dev — DOIT correspondre à INTERNAL_API_SECRET dans frontend/.env.local.
# En production, remplacer par une valeur aléatoire forte (secrets.token_urlsafe(32)).
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "dev-konis-internal-secret")
