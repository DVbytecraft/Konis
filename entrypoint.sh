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
    # Forcer role='admin' + lier à l'Entreprise initiale
    # createsuperuser peut laisser role='' ou 'boutique', et ne lie pas l'entreprise
    python manage.py shell -c "
from django.contrib.auth import get_user_model
from core.models import Entreprise
User = get_user_model()
nom = '${KONIS_ENTREPRISE_NOM:-KONIS}'
e, created = Entreprise.objects.get_or_create(nom=nom)
if created:
    print(f'==> [KONIS] Entreprise creee : {nom}')
updated = User.objects.filter(is_superuser=True).exclude(role='supreme_admin').update(role='supreme_admin', entreprise=e)
User.objects.filter(is_superuser=True, entreprise__isnull=True).update(entreprise=e)
print(f'==> [KONIS] Superuser(s) mis a jour : role=supreme_admin, entreprise={nom}')
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
