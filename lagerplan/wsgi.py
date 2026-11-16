"""WSGI entry point, used by Gunicorn: `gunicorn lagerplan.wsgi:application`."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lagerplan.settings")

application = get_wsgi_application()
