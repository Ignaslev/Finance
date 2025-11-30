import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Load .env (safe for local dev; in prod use real env vars)
load_dotenv(BASE_DIR / ".env")

def env(name, default=None, *, required=False):
    value = os.getenv(name, default)
    if required and value is None:
        raise ImproperlyConfigured(f"Missing required env var: {name}")
    return value

SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)

DEBUG = env("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes", "on")

# Comma-separated list from .env
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "finance",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        'DIRS': [],
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
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# 2. INTERNATIONALIZATION
# moneycoach/settings.py

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # <--- MUST BE HERE (Between Session and Common)
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# --- INTERNATIONALIZATION ---

# 1. Default language (Force Lithuanian for now to test)
LANGUAGE_CODE = 'lt'

TIME_ZONE = 'UTC'
USE_TZ = True

# 2. Enable Text Translation
USE_I18N = True

# 3. DISABLE Number/Date Localization (Crucial for Charts/CSS!)
USE_L10N = False
USE_THOUSAND_SEPARATOR = False
DECIMAL_SEPARATOR = '.'

from django.utils.translation import gettext_lazy as _

LANGUAGES = [
    ('en', _('English')),
    ('lt', _('Lithuanian')),
]

# 4. Define where the translation files live
import os
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# ADD THIS BLOCK:
import os
STATICFILES_DIRS = [
    BASE_DIR / "moneycoach" / "static",
]

# Where Django COLLECTS the files for Production (Destination)
# This folder is created automatically when you run collectstatic
STATIC_ROOT = BASE_DIR / "staticfiles"

# Canonical categories used across models, views, and seeding
DEFAULT_CATEGORIES = [
    "Income", "Cash", "Dining", "Fitness & Health",
    "Groceries", "Shopping", "Crypto", "Utilities",
    "Other", "Subscriptions", "Transportation",
]


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/overview/"
LOGOUT_REDIRECT_URL = "login"

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATES[0]["DIRS"] = [
    BASE_DIR / "moneycoach" / "templates",  # project-level templates (where base.html is)
    # BASE_DIR / "templates",               # optional if you make a /templates folder later
]

TEACH_AI_UNLOCK = 20                # unlock after 20 user labels
AI_AUTOCAT_COOLDOWN_MIN = 10        # don't run more than once per 10 minutes per user
# (your existing AUTO_APPLY_THRESHOLD / AUTO_CHANGE_THRESHOLD / BATCH_SIZE stay as-is)
