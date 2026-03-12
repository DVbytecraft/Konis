#!/bin/sh
# Entrypoint de production KONIS — backend Django/Gunicorn
# Ordre : staticfiles dir → migrations → collectstatic → superuser → Gunicorn
set -e

# ── 1. Créer STATIC_ROOT si absent ────────────────────────────────────────────
# Django (et WhiteNoise) émettent un warning si le répertoire n'existe pas au
# démarrage. Le créer avant collectstatic supprime ce warning.
mkdir -p /app/staticfiles

# ── 2. Migrations ─────────────────────────────────────────────────────────────
echo "==> [KONIS] Exécution des migrations..."
python manage.py migrate --noinput

# ── 3. Fichiers statiques ──────────────────────────────────────────────────────
echo "==> [KONIS] Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear

# ── 4. Superuser initial (optionnel) ──────────────────────────────────────────
# Déclenché uniquement si les 3 variables sont définies.
# || true : silencieux si l'utilisateur existe déjà.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && \
   [ -n "$DJANGO_SUPERUSER_EMAIL" ] && \
   [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> [KONIS] Création du superuser '$DJANGO_SUPERUSER_USERNAME'..."
    python manage.py createsuperuser --no-input || true
fi

# ── 5. Gunicorn ────────────────────────────────────────────────────────────────
# --bind 0.0.0.0:8000 : écoute sur toutes les interfaces réseau du conteneur.
#   Requis par App Platform — sans ça, le health check et le trafic externe
#   ne peuvent pas atteindre le process (127.0.0.1 = loopback uniquement).
# --config gunicorn.conf.py : workers, threads, timeouts, logging (voir le fichier).
echo "==> [KONIS] Démarrage de Gunicorn sur 0.0.0.0:8000..."
exec gunicorn konis.wsgi:application \
     --bind 0.0.0.0:8000 \
     --config gunicorn.conf.py
