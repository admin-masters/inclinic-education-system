from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the custom .env file path
load_dotenv("/var/www/secrets/.env")  # ① load the file

import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-for-dev')  # Keep secret in production

DEBUG = False 

ALLOWED_HOSTS = [
    'new.cpdinclinic.co.in',
]

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
    'rest_framework',
    'admin_dashboard',
    'campaign_management',
    'collateral_management',
    'shortlink_management.apps.ShortlinkManagementConfig',
    'sharing_management',
    'doctor_viewer.apps.DoctorViewerConfig',
    'social_django',
    'corsheaders',
    'django_celery_beat',
    'user_management.apps.UserManagementConfig',
    'reporting_etl.apps.ReportingEtlConfig',
]

# ----------------------------------------------------------------------------
# Middleware
# ----------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',  
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'utils.context_processors.recaptcha_site_key',
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# ----------------------------------------------------------------------------
# Database
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
# Password Validation
# ----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
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
    'django.contrib.auth.backends.ModelBackend',
)

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.getenv("SOCIAL_AUTH_GOOGLE_OAUTH2_KEY")           
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv("SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET")     

RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")                                  
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")                              

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
SOCIAL_AUTH_URL_NAMESPACE = 'social'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
ADMIN_DASHBOARD_LINK = '/admin/dashboard/'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}

CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = ['https://*.cpdinclinic.co.in']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # if behind Nginx or load balancer
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
