#!/bin/sh
# Entrypoint de production KONIS — backend Django/Gunicorn
# Ordre : staticfiles dir → migrations → superuser → Gunicorn
set -e

# ── 1. Garantir STATIC_ROOT ───────────────────────────────────────────────────
# Les fichiers statiques sont déjà collectés au BUILD (Dockerfile.prod).
# mkdir -p est un filet de sécurité uniquement — ne re-exécute PAS collectstatic
# pour éviter de vider le répertoire avec --clear avant que Gunicorn démarre.
mkdir -p /app/staticfiles

# ── 2. Migrations ─────────────────────────────────────────────────────────────
echo "==> [KONIS] Exécution des migrations..."
python manage.py migrate --noinput

# ── 3. Superuser initial (optionnel) ──────────────────────────────────────────
# Déclenché uniquement si les 3 variables sont définies.
# || true : silencieux si l'utilisateur existe déjà.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && \
   [ -n "$DJANGO_SUPERUSER_EMAIL" ] && \
   [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> [KONIS] Création du superuser '$DJANGO_SUPERUSER_USERNAME'..."
    python manage.py createsuperuser --no-input || true
fi

# ── 4. Gunicorn ────────────────────────────────────────────────────────────────
# --bind 0.0.0.0:8000 : écoute sur toutes les interfaces réseau du conteneur.
#   Requis par App Platform — sans ça, le health check et le trafic externe
#   ne peuvent pas atteindre le process (127.0.0.1 = loopback uniquement).
# --config gunicorn.conf.py : workers, threads, timeouts, logging (voir le fichier).
echo "==> [KONIS] Démarrage de Gunicorn sur 0.0.0.0:8000..."
exec gunicorn konis.wsgi:application \
     --bind 0.0.0.0:8000 \
     --config gunicorn.conf.py
