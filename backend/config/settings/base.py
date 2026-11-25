from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[3]
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / "backend" / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

INSTALLED_APPS = [
    "apps.accounts.admin_site.LocalAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_filters",
    "rest_framework",
    "apps.accounts",
    "apps.core",
    "apps.audit",
    "apps.licensing",
    "apps.academics",
    "apps.attendance",
    "apps.fees",
    "apps.examinations",
    "apps.hr",
    "apps.timetables",
    "apps.students",
    "apps.admissions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.RequestAuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "backend" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="5433"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "ATOMIC_REQUESTS": True,
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "backend" / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "backend" / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "config.exception_handlers.api_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.sessions.LocalSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

AUTHENTICATION_BACKENDS = ["apps.accounts.access.LocalBackend"]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "apps.accounts.authentication.csrf_rejected"
APP_SESSION_IDLE = max(1, env.int("APP_SESSION_IDLE", default=1800))
APP_SESSION_MAX = max(1, env.int("APP_SESSION_MAX", default=43200))
SESSION_COOKIE_AGE = APP_SESSION_MAX
APP_LOGIN_WINDOW = max(1, env.int("APP_LOGIN_WINDOW", default=300))
APP_LOGIN_LIMIT = max(1, env.int("APP_LOGIN_LIMIT", default=8))
APP_LOGIN_IP_LIMIT = max(APP_LOGIN_LIMIT, env.int("APP_LOGIN_IP_LIMIT", default=60))

LICENSE_PUBLIC_KEYS = {}
LICENSE_PUBLIC_KEYS_FILE = env("LICENSE_PUBLIC_KEYS_FILE", default="")
LICENSE_MAX_GRACE_DAYS = min(14, max(0, env.int("LICENSE_MAX_GRACE_DAYS", default=7)))
LICENSE_GRACE_WRITES = env.bool("LICENSE_GRACE_WRITES", default=False)
LICENSE_CLOCK_TOLERANCE = max(0, env.int("LICENSE_CLOCK_TOLERANCE", default=300))


STUDENT_DOCUMENT_KINDS = env.list(
    "STUDENT_DOCUMENT_KINDS",
    default=[
        "admission-form",
        "academic-record",
        "photo",
        "transfer-certificate",
        "other",
    ],
)
STUDENT_DOCUMENT_MAX_BYTES = min(
    10 * 1024 * 1024, max(1024, env.int("STUDENT_DOCUMENT_MAX_BYTES", default=5 * 1024 * 1024))
)
