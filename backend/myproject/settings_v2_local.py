"""Local-only settings for InClinic v2 migration verification."""

from .settings import *  # noqa: F401,F403
from .local_services import LOCAL_SYSTEM_SERVICES


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {
        "handlers": ["stderr"],
        "level": "ERROR",
    },
}

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

LOCAL_SERVICE_URLS = {
    name: service.url
    for name, service in LOCAL_SYSTEM_SERVICES.items()
}

SITE_URL = LOCAL_SERVICE_URLS["inclinic"]
INCLINIC_BASE_URL = LOCAL_SERVICE_URLS["inclinic"]
RFA_BASE_URL = LOCAL_SERVICE_URLS["rfa"]
PE_BASE_URL = LOCAL_SERVICE_URLS["pe"]
SHORTLINK_REDIRECT_DOMAIN = INCLINIC_BASE_URL
FIELD_REP_REDIRECT_BASE_URL = RFA_BASE_URL
CSRF_TRUSTED_ORIGINS = [
    INCLINIC_BASE_URL,
    RFA_BASE_URL,
    PE_BASE_URL,
]
CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS

LOCAL_RUNTIME_DIR = BACKEND_DIR / ".local_runtime"
STATIC_ROOT = LOCAL_RUNTIME_DIR / "staticfiles"
MEDIA_ROOT = LOCAL_RUNTIME_DIR / "media"
MEDIA_URL = "/media/"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "inclinic_live",
        "USER": "root",
        "PASSWORD": "",
        "HOST": "localhost",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    "reporting": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "inclinic_live",
        "USER": "root",
        "PASSWORD": "",
        "HOST": "localhost",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    "master": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "rfa_master_dev",
        "USER": "root",
        "PASSWORD": "",
        "HOST": "localhost",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
}

MASTER_DB_ALIAS = "master"

# RFA dev links are often pasted/tested after the short production token window.
# Keep this override local-only so expired pasted links can still exercise the
# InClinic field-rep flow without changing production validation.
PUBLISHER_JWT_LEEWAY_SECONDS = 24 * 60 * 60
