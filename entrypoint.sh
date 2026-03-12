#!/bin/sh
# Entrypoint de production KONIS — backend Django/Gunicorn
# Exécute les migrations, collecte les statics, crée le superuser si nécessaire, puis lance Gunicorn.
set -e

echo "==> [KONIS] Vérification des migrations en attente..."
python manage.py migrate --check 2>/dev/null || true

echo "==> [KONIS] Exécution des migrations..."
python manage.py migrate --noinput

echo "==> [KONIS] Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear

# Création automatique du superuser si les 3 variables sont définies.
# Variables requises : DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD
# Si le compte existe déjà, la commande échoue silencieusement (|| true).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && \
   [ -n "$DJANGO_SUPERUSER_EMAIL" ] && \
   [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> [KONIS] Création du superuser '$DJANGO_SUPERUSER_USERNAME' (ignoré s'il existe déjà)..."
    python manage.py createsuperuser --no-input || true
fi

echo "==> [KONIS] Démarrage de Gunicorn (config : gunicorn.conf.py)..."
# --bind explicite pour App Platform (0.0.0.0:8000 requis — écoute sur toutes les interfaces).
# gunicorn.conf.py définit aussi bind = "0.0.0.0:8000" — la valeur CLI prend la priorité.
exec gunicorn konis.wsgi:application \
     --bind 0.0.0.0:8000 \
     --config gunicorn.conf.py
