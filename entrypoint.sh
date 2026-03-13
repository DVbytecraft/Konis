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
    # Forcer role='admin' sur le superuser — createsuperuser peut laisser role='' ou 'boutique'
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
updated = User.objects.filter(is_superuser=True).exclude(role='admin').update(role='admin')
print(f'==> [KONIS] {updated} superuser(s) mis a jour avec role=admin')
" || true
fi

# ── 4. Gunicorn ────────────────────────────────────────────────────────────────
# --bind 0.0.0.0:${PORT:-8000} : respecte le PORT injecté par DigitalOcean App Platform.
#   DO injecte PORT selon http_port dans app.yaml — hardcoder 8000 cause un 502
#   si DO attend un port différent. Fallback 8000 pour docker-compose local.
# --config gunicorn.conf.py : workers, threads, timeouts, logging (voir le fichier).
_PORT="${PORT:-8000}"
echo "==> [KONIS] Démarrage de Gunicorn sur 0.0.0.0:${_PORT}..."
exec gunicorn konis.wsgi:application \
     --bind "0.0.0.0:${_PORT}" \
     --config gunicorn.conf.py
