#!/bin/sh
# Entrypoint de production KONIS — backend Django/Gunicorn
# Exécute les migrations, collecte les statics, puis lance Gunicorn.
set -e

echo "==> [KONIS] Vérification de la connexion à la base de données..."
python manage.py migrate --check 2>/dev/null || true

echo "==> [KONIS] Exécution des migrations..."
python manage.py migrate --noinput

echo "==> [KONIS] Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear

echo "==> [KONIS] Démarrage de Gunicorn (config : gunicorn.conf.py)..."
exec gunicorn konis.wsgi --config gunicorn.conf.py
