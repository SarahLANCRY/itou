from ._sentry import sentry_init
from .base import *


ALLOWED_HOSTS = ["127.0.0.1", ".cleverapps.io", "demo.inclusion.beta.gouv.fr", "demo.emplois.inclusion.beta.gouv.fr"]

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "HOST": os.environ.get("POSTGRESQL_ADDON_HOST"),
        "PORT": os.environ.get("POSTGRESQL_ADDON_PORT"),
        "NAME": os.environ.get("POSTGRESQL_ADDON_DB"),
        "USER": os.environ.get("POSTGRESQL_ADDON_USER"),
        "PASSWORD": os.environ.get("POSTGRESQL_ADDON_PASSWORD"),
    }
}

ITOU_ENVIRONMENT = "DEMO"
ITOU_PROTOCOL = "https"
ITOU_FQDN = "demo.emplois.inclusion.beta.gouv.fr"
ITOU_EMAIL_CONTACT = "contact+demo@inclusion.beta.gouv.fr"
DEFAULT_FROM_EMAIL = "noreply+demo@inclusion.beta.gouv.fr"

sentry_init(dsn=os.environ["SENTRY_DSN_DEMO"])

ASP_ITOU_PREFIX = "XXXXX"

SHOW_TEST_ACCOUNTS_BANNER = True
