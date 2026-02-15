"""
Django settings for Inclinic Education System
──────────────────────────────────────────────
All project code, templates, static files and media remain
under:  /var/www/inclinic-education-system/backend
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# ──────────────────────────────────────────────────────────────
# 0   Environment variables
# ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv("/var/www/secrets/.env")

# ──────────────────────────────────────────────────────────────
# 1   Paths
# ──────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent          # …/backend
PROJECT_DIR = BACKEND_DIR.parent                              # …/inclinic-education-system

# you may still use PROJECT_DIR elsewhere if needed
# BASE_DIR = BACKEND_DIR                                        # ← key change

# ──────────────────────────────────────────────────────────────
# 2   Security
# ──────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-default-key-for-dev")
DEBUG = True
ALLOWED_HOSTS = [
    ".cpdinclinic.co.in",
    "13.200.145.110",
    "127.0.0.1",
    "localhost",
]

CSRF_TRUSTED_ORIGINS   = ["https://*.cpdinclinic.co.in"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE      = True
SESSION_COOKIE_SECURE   = True

# ──────────────────────────────────────────────────────────────
# 3   Installed apps
# ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "admin_dashboard",
    "campaign_management",
    "collateral_management",
    "shortlink_management.apps.ShortlinkManagementConfig",
    "sharing_management.apps.SharingManagementConfig",
    "doctor_viewer.apps.DoctorViewerConfig",
    "social_django",
    "corsheaders",
    "django_celery_beat",
    "user_management.apps.UserManagementConfig",
    "reporting_etl.apps.ReportingEtlConfig",
]

# ──────────────────────────────────────────────────────────────
# 4   Middleware
# ──────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "myproject.urls"
WSGI_APPLICATION = "myproject.wsgi.application"

# ──────────────────────────────────────────────────────────────
# 5   Templates  (reads from backend/templates)
# ──────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BACKEND_DIR / "templates"],   # ← points to backend/templates
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "utils.context_processors.recaptcha_site_key",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "social_django.context_processors.backends",
                "social_django.context_processors.login_redirect",
            ],
        },
    },
]
WSGI_APPLICATION = 'myproject.wsgi.application'
# ──────────────────────────────────────────────────────────────
# 6   Database
# ──────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "inclinic_local",
        "USER": "django_root",
        "PASSWORD": "d/x*6R5]D[9.@12",
        "HOST": "localhost",
        "PORT": "3306",
    },
    "reporting": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "healthcare_reports_2",
        "USER": "admin",
        "PASSWORD": "kodwyb-6Muqdo-cudxew",
        "HOST": "reporting-server-live.cbnobb8kfeuq.ap-south-1.rds.amazonaws.com",
        "PORT": "3306",
        "OPTIONS": {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'master': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'healthcare_forms_2',    # Your DB name
        'USER': 'admin',                # Username shown in your screenshot
        'PASSWORD': 'fizxyZ-rovpat-memri5',    # Enter the correct root password
        'HOST': 'master-db-new-system.cbnobb8kfeuq.ap-south-1.rds.amazonaws.com',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
}

AUTH_USER_MODEL = "user_management.User"

# ──────────────────────────────────────────────────────────────
# 7   Password validation
# ──────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# ──────────────────────────────────────────────────────────────
# 8   i18n / timezone
# ──────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_I18N = USE_L10N = USE_TZ = True

# ──────────────────────────────────────────────────────────────
# 9   Static & media  (stay under backend/)
# ──────────────────────────────────────────────────────────────
STATIC_URL  = "/static/"

FRONTEND_DIST = Path(
    "/var/www/inclinic-education-system/frontend/admin-console/dist"
)
# Only add to STATICFILES_DIRS if the directory exists
if FRONTEND_DIST.exists():
    STATICFILES_DIRS = [FRONTEND_DIST]
else:
    STATICFILES_DIRS = []

STATIC_ROOT  = BACKEND_DIR / "staticfiles"
STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
# MEDIA_URL   = "/media/"
MEDIA_URL   = "/media/"
MEDIA_ROOT = Path("/var/www/inclinic-media")

# ──────────────────────────────────────────────────────────────
# 10  Social auth / reCAPTCHA
# ──────────────────────────────────────────────────────────────
AUTHENTICATION_BACKENDS = (
    "social_core.backends.google.GoogleOAuth2",
    "django.contrib.auth.backends.ModelBackend",
)

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY    = os.getenv("SOCIAL_AUTH_GOOGLE_OAUTH2_KEY")
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv("SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET")

RECAPTCHA_SITE_KEY   = os.getenv("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

LOGIN_REDIRECT_URL = '/campaigns/manage-data/'
LOGOUT_REDIRECT_URL = "/"
SOCIAL_AUTH_URL_NAMESPACE = "social"

ADMIN_DASHBOARD_LINK = "/admin/dashboard/"
SHORTLINK_REDIRECT_DOMAIN = 'https://new.cpdinclinic.co.in'
# ──────────────────────────────────────────────────────────────
# 11  Django REST framework
# ──────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
}

# ──────────────────────────────────────────────────────────────
# 12  CORS
# ──────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ──────────────────────────────────────────────────────────────
# 13  Logging (errors to file + stderr)
# ──────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "/var/log/inclinic/django-error.log",
            "formatter": "verbose",
        },
    },
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s "
                      "%(name)s:%(lineno)s %(message)s"
        },
    },
    "root": {
        "handlers": ["stderr", "file"],
        "level": "ERROR",
    },
}
# ----------------------------------------------------------------------------
# Email Configuration (SMTP with Gmail)
# ----------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")  # your-email@gmail.com
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")  # App Password
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


X_FRAME_OPTIONS = 'SAMEORIGIN'

# JWT validation (master publishing system -> PE system)
PUBLISHER_JWT_SECRET = os.getenv("PUBLISHER_JWT_SECRET", "")         # HS256
PUBLISHER_JWT_PUBLIC_KEY = os.getenv("PUBLISHER_JWT_PUBLIC_KEY", "") # RS256/ES256 etc.
PUBLISHER_JWT_ALGORITHMS = os.getenv("PUBLISHER_JWT_ALGORITHMS", "HS256").split(",")
PUBLISHER_JWT_ISSUER = os.getenv("PUBLISHER_JWT_ISSUER", "project1")
PUBLISHER_JWT_AUDIENCE = os.getenv("PUBLISHER_JWT_AUDIENCE", "project2")
PUBLISHER_JWT_LEEWAY_SECONDS = int(os.getenv("PUBLISHER_JWT_LEEWAY_SECONDS", "30"))

# Master DB table names (configurable, since master system schema naming may differ)
MASTER_CAMPAIGN_DB_TABLE = "campaign_campaign"
MASTER_BRAND_DB_TABLE = "campaign_brand"

# Toggle: when False, SSO settings do NOT consult environment variables at all.
PUBLISHER_SSO_USE_ENV = False

def _sso_setting(name: str, default):
    if PUBLISHER_SSO_USE_ENV:
        return os.getenv(name, default)
    return default

PUBLISHER_SSO_SHARED_SECRET = _sso_setting(
    "PUBLISHER_SSO_SHARED_SECRET",
    "CHANGE-ME-TO-A-LONG-RANDOM-STRING",
)

PUBLISHER_JWT_SECRET = PUBLISHER_SSO_SHARED_SECRET
