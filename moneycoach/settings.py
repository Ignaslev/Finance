import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import dj_database_url  # Added for Railway
import copy
from django.utils.log import DEFAULT_LOGGING

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env (safe for local dev; in prod use real env vars)
load_dotenv(BASE_DIR / ".env")

def env_list(name, default=""):
    raw = os.getenv(name, default) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def env(name, default=None, *, required=False):
    value = os.getenv(name, default)
    if required and value is None:
        raise ImproperlyConfigured(f"Missing required env var: {name}")
    return value

def env_bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-me", required=False)

# Default to False in production
DEBUG = env("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes", "on")
IS_PROD = not DEBUG

# Allow all hosts in production (Railway handles routing), or restrict if preferred
# Default: safe for local dev; in prod set DJANGO_ALLOWED_HOSTS and DJANGO_CSRF_TRUSTED_ORIGINS
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost,http://127.0.0.1"
)


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
    'finance.middleware.UserPreferredLanguageMiddleware',
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
                "finance.context_processors.pending_delete_banner",
                "finance.context_processors.subscription_access",
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

CACHE_BACKEND = env("DJANGO_CACHE_BACKEND", "database" if IS_PROD else "locmem").lower()
if CACHE_BACKEND == "database":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": env("DJANGO_CACHE_TABLE", "moneycompass_cache"),
            "TIMEOUT": int(env("DJANGO_CACHE_TIMEOUT", "900")),
            "OPTIONS": {"MAX_ENTRIES": int(env("DJANGO_CACHE_MAX_ENTRIES", "10000"))},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "moneycompass-dev-cache",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGGING = copy.deepcopy(DEFAULT_LOGGING)

# Stop emailing ADMINS for bot Host-header probes (DisallowedHost).
LOGGING["loggers"]["django.security.DisallowedHost"] = {
    "handlers": ["console"],   # keep it in logs (journald)
    "level": "ERROR",
    "propagate": False,        # don't bubble to django.request -> email
}


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
STATIC_URL = '/static/'
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
    "Other", "Subscriptions", "Transportation", "Internal transfer",
]

TEACH_AI_UNLOCK = 20
AI_AUTOCAT_COOLDOWN_MIN = 10

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",              # email login
    "django.contrib.auth.backends.ModelBackend",   # keep username login possible (admin etc.)
]


# ----------------------------
# Email configuration
# ----------------------------
# Allow running DEBUG=False on staging while still using console email.
EMAIL_MODE = env("EMAIL_MODE", "console").lower()  # console | smtp

ADMINS = [("MoneyCompass Admin", env("ADMIN_ALERT_EMAIL", "admin@moneycompass.lt"))]

if EMAIL_MODE == "smtp":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", required=True)
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))

    # Support both STARTTLS (587) and SSL (465)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
    EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)

    # TLS and SSL must not both be True
    if EMAIL_USE_SSL:
        EMAIL_USE_TLS = False

    EMAIL_HOST_USER = env("EMAIL_HOST_USER", required=True)
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", required=True)
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", required=True)
else:
    # Default: console backend (safe for staging/dev)
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@moneycoach.local")

SERVER_EMAIL = env("SERVER_EMAIL", DEFAULT_FROM_EMAIL)


# ---------------------------------------------------------
# Production security hardening
# ---------------------------------------------------------
TRUSTED_PROXY_IPS = env_list("DJANGO_TRUSTED_PROXY_IPS", "127.0.0.1,::1")

# If you're behind a proxy/load balancer (nginx, Railway, etc.)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# IMPORTANT:
# While you are still on plain HTTP (no TLS), keep these False in .env.
# Later, when HTTPS is enabled, flip them to True.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", IS_PROD)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", IS_PROD)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", IS_PROD)


# Sensible defaults
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = env_bool("DJANGO_CSRF_COOKIE_HTTPONLY", True)
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

if IS_PROD:
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "False").lower() in ("1","true","yes","on")
    SECURE_HSTS_PRELOAD = env("DJANGO_HSTS_PRELOAD", "False").lower() in ("1","true","yes","on")
else:
    SECURE_HSTS_SECONDS = 0

REQUIRE_EMAIL_VERIFICATION = env("REQUIRE_EMAIL_VERIFICATION", "True").lower() in ("1", "true", "yes", "on")

# --- Abuse-prevention quotas (tweak later if needed) ---
MAX_IMPORTS_PER_DAY = int(os.getenv("MAX_IMPORTS_PER_DAY", "20"))
MAX_ROWS_PER_IMPORT = int(os.getenv("MAX_ROWS_PER_IMPORT", "20000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))  # 20MB

MAX_MONEY_SOURCES_PER_USER = int(os.getenv("MAX_MONEY_SOURCES_PER_USER", "25"))
MAX_CATEGORIES_PER_USER = int(os.getenv("MAX_CATEGORIES_PER_USER", "25"))
MAX_GOALS_PER_USER = int(os.getenv("MAX_GOALS_PER_USER", "50"))

BETA_REGISTRATION_ENABLED = env_bool("BETA_REGISTRATION_ENABLED", True)
BETA_USER_LIMIT = int(os.getenv("BETA_USER_LIMIT", "100"))
BETA_ACCESS_CODE = env("BETA_ACCESS_CODE", "")
BETA_FREE_DAYS = int(os.getenv("BETA_FREE_DAYS", "365"))
TRIAL_FREE_DAYS = int(os.getenv("TRIAL_FREE_DAYS", "14"))

# Stripe Billing
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_MONTHLY = env("STRIPE_PRICE_MONTHLY", "price_1TmwO2Ftoq7RCq7B35ByJTWR")
STRIPE_PRICE_YEARLY = env("STRIPE_PRICE_YEARLY", "price_1TmwO2Ftoq7RCq7BX5gGrdho")
