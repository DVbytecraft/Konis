# Par défaut : dev. Pour la prod, définir DJANGO_SETTINGS_MODULE=konis.settings.prod
from .dev import *  # noqa: F401, F403
