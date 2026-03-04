#!/usr/bin/env bash
# Build Render – exécuté par Render comme buildCommand si besoin
set -e
pip install -r requirements.txt
python manage.py collectstatic --noinput
