from pathlib import Path

from .settings import *


DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

DOCS_RUNTIME_DIR = BASE_DIR / "tmp" / "docs" / "demo_runtime"
STATIC_ROOT = DOCS_RUNTIME_DIR / "staticfiles"
MEDIA_ROOT = DOCS_RUNTIME_DIR / "media"
MEDIA_URL = "/media/"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DOCS_RUNTIME_DIR / "default.sqlite3"),
    },
    "reporting": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DOCS_RUNTIME_DIR / "reporting.sqlite3"),
    },
    "master": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DOCS_RUNTIME_DIR / "master.sqlite3"),
    },
}

MASTER_DB_ALIAS = "master"

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

SITE_URL = "http://127.0.0.1:8000"
SHORTLINK_REDIRECT_DOMAIN = SITE_URL
FIELD_REP_REDIRECT_BASE_URL = SITE_URL

PUBLISHER_JWT_SECRET = "docs-demo-shared-secret-2026-pack"
PUBLISHER_JWT_ALGORITHMS = ["HS256"]
PUBLISHER_JWT_ISSUER = "project1"
PUBLISHER_JWT_AUDIENCE = "project2"

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
