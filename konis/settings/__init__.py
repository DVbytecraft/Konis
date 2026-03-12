"""
Point d'entrée du package settings.

Charge automatiquement prod.py ou dev.py selon DJANGO_SETTINGS_MODULE :
  - konis.settings.prod  → settings production (DigitalOcean, Render, VPS…)
  - konis.settings       → dev.py  (manage.py local sans variable explicite)
  - absent               → dev.py

wsgi.py et asgi.py ont pour défaut 'konis.settings.prod', ce qui garantit
que DigitalOcean charge prod.py même si DJANGO_SETTINGS_MODULE n'est pas
défini manuellement dans les variables d'environnement App Platform.
manage.py garde 'konis.settings' comme défaut → dev.py en local.
"""
import os

_env = os.environ.get("DJANGO_SETTINGS_MODULE", "")

if _env == "konis.settings.prod":
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403
