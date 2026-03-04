# PostgreSQL en local — KONIS V0

## Prérequis

1. **Docker Desktop** : démarrer Docker Desktop avant les commandes.
2. **Variables** : créer `.env` depuis `.env.example` (ou exporter `DATABASE_URL`).

## Commandes (ordre exact)

```bash
# 1. Démarrer Postgres
cd konis
docker compose up -d

# 2. Définir DATABASE_URL (PowerShell)
$env:DATABASE_URL="postgres://konis:CHANGE_ME@localhost:5432/konis"
$env:DJANGO_SETTINGS_MODULE="konis.settings.dev"

# 2bis. Linux/macOS
export DATABASE_URL="postgres://konis:CHANGE_ME@localhost:5432/konis"
export DJANGO_SETTINGS_MODULE="konis.settings.dev"

# 3. Migrations
python manage.py migrate

# 4. Seed
python manage.py seed --no-input

# 5. Tests
python manage.py test api

# 6. Serveur
python manage.py runserver

# 7. Health (autre terminal)
curl http://127.0.0.1:8000/api/health/
# Attendu: {"status":"ok","db":"ok","version":"v0"}

# 8. Preuve DB
python scripts/proof_postgres.py
# Attendu: ENGINE: django.db.backends.postgresql, PostgreSQL: OUI, comptages
```

## Sans DATABASE_URL

Django **refuse** de démarrer :

```
django.core.exceptions.ImproperlyConfigured: DATABASE_URL est obligatoire en dev.
```

## Windows : UnicodeDecodeError psycopg2 (byte 0xe9)

**Cause** : Quand PostgreSQL n’est pas lancé, la connexion échoue. Sur Windows (locale FR), libpq retourne un message d’erreur en CP1252 (ex. "refusée"). psycopg2 le décode en UTF-8 → `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9`.

**Fix** :
1. Démarrer **Docker Desktop**, puis `docker compose up -d` **avant** migrate/runserver.
2. Définir `PGCLIENTENCODING=UTF8` (optionnel, précaution) :
   - PowerShell : `$env:PGCLIENTENCODING="UTF8"`
   - Bash : `export PGCLIENTENCODING=UTF8`
