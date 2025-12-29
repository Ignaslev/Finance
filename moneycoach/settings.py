import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import dj_database_url  # Added for Railway

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env (safe for local dev; in prod use real env vars)
load_dotenv(BASE_DIR / ".env")

def env(name, default=None, *, required=False):
    value = os.getenv(name, default)
    if required and value is None:
        raise ImproperlyConfigured(f"Missing required env var: {name}")
    return value

SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-me", required=False)

# Default to False in production
DEBUG = env("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes", "on")

# Allow all hosts in production (Railway handles routing), or restrict if preferred
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["https://*.railway.app", "https://*.up.railway.app"]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "finance",
    "accounts",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Critical for static files
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'moneycoach.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "moneycoach" / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "finance.context_processors.onboarding",
                "finance.context_processors.ai_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = 'moneycoach.wsgi.application'

# Database
# Auto-switch: SQLite locally, Postgres on Railway
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNATIONALIZATION ---
LANGUAGE_CODE = 'lt'
TIME_ZONE = 'UTC'
USE_TZ = True
USE_I18N = True
USE_L10N = False  # Critical for charts
USE_THOUSAND_SEPARATOR = False
DECIMAL_SEPARATOR = '.'

from django.utils.translation import gettext_lazy as _
LANGUAGES = [
    ('en', _('English')),
    ('lt', _('Lithuanian')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

# --- STATIC FILES ---
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "moneycoach" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Compression for Production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- APP CONSTANTS ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "overview"   # optional but recommended
LOGOUT_REDIRECT_URL = "login"

DEFAULT_CATEGORIES = [
    "Income", "Cash", "Dining", "Fitness & Health",
    "Groceries", "Shopping", "Crypto", "Utilities",
    "Other", "Subscriptions", "Transportation",
]

TEACH_AI_UNLOCK = 20
AI_AUTOCAT_COOLDOWN_MIN = 10

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",              # email login
    "django.contrib.auth.backends.ModelBackend",   # keep username login possible (admin etc.)
]


# TESTING ONLY
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "no-reply@moneycoach.local"
