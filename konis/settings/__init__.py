"""
Point d'entrée du package settings.

Charge automatiquement prod.py ou dev.py selon DJANGO_SETTINGS_MODULE :
  - konis.settings.prod  → settings production (DigitalOcean, Render, VPS…)
  - konis.settings       → même chose si DJANGO_SETTINGS_MODULE pointe ici
  - tout autre valeur    → dev.py (localhost, Docker local)

Pourquoi ce fichier existe :
  wsgi.py fait os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'konis.settings').
  Sans ce switch, quand DO ne définit pas la variable, Django charge ce fichier
  et tombe sur dev.py → ALLOWED_HOSTS = localhost → DisallowedHost en prod.
"""
import os

_env = os.environ.get("DJANGO_SETTINGS_MODULE", "")

if _env == "konis.settings.prod":
    from .prod import *  # noqa: F401, F403
else:
    from .dev import *  # noqa: F401, F403
