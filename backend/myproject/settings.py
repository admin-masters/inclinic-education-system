"""
myproject/settings.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-for-dev')  # Keep secret in production

DEBUG = True # For development only

ALLOWED_HOSTS = ['new.cpdinclinic.co.in']

# ----------------------------------------------------------------------------
# Apps
# ----------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 'user_management',
    'rest_framework',
    'admin_dashboard',  
    'campaign_management',
    'collateral_management',
    'shortlink_management.apps.ShortlinkManagementConfig',
    'sharing_management',
    'doctor_viewer.apps.DoctorViewerConfig',
    # 3rd-party apps
    'social_django',           # for Google OAuth
    # 'rest_framework',        # if using DRF
    'corsheaders',           # if needed for cross-origin requests
    'django_celery_beat',
    # Our custom app
    'user_management.apps.UserManagementConfig',
    # 'admin_dashboard.apps.AdminDashboardConfig',
    'reporting_etl.apps.ReportingEtlConfig',
]

# ----------------------------------------------------------------------------
# Middleware
# ----------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'corsheaders.middleware.CorsMiddleware', # if needed
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [ BASE_DIR / 'templates' ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'utils.context_processors.recaptcha_site_key',
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',

                # Needed for social auth
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# ----------------------------------------------------------------------------
# Database: MySQL example
# ----------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'myproject_dev',
        'USER': 'user_root',
        'PASSWORD': '6k9I7Lz-|[h',
        'HOST': '13.200.145.110',
        'PORT': '3306',
    },
    'reporting': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'myproject_reporting',
        'USER': 'user_root',
        'PASSWORD': '6k9I7Lz-|[h',
        'HOST': '13.200.145.110',
        'PORT': '3306',
    }
}

# ----------------------------------------------------------------------------
# Custom User Model
# ----------------------------------------------------------------------------
AUTH_USER_MODEL = 'user_management.User'

# ----------------------------------------------------------------------------
# Password validation
# ----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    # Add more if needed
]

# ----------------------------------------------------------------------------
# Internationalization / Timezone
# ----------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ----------------------------------------------------------------------------
# Static Files
# ----------------------------------------------------------------------------
STATIC_URL = '/static/'

# ----------------------------------------------------------------------------
# Social Auth Config (Google OAuth)
# ----------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'django.contrib.auth.backends.ModelBackend',  # default
)
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.getenv('SOCIAL_AUTH_GOOGLE_OAUTH2_KEY', '')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv('SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET', '')


RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY")


# Where to redirect after successful login/logout
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

SOCIAL_AUTH_URL_NAMESPACE = 'social'

# In production, also set:
# CSRF_TRUSTED_ORIGINS = ['new.cpdinclinic.co.in']
# SESSION_COOKIE_SECURE = True
# etc.

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
ADMIN_DASHBOARD_LINK = '/admin/dashboard/'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',  # Admin UI uses session auth
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}
CORS_ALLOW_ALL_ORIGINS = True
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:3000",              # React/Vite dev server
#     "https://admin.inditech.com",         # your deployed frontend
# ]

