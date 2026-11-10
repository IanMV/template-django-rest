import os
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.getenv("SECRET_KEY")
if (
    not SECRET_KEY
    or len(SECRET_KEY.strip()) < 50
    or SECRET_KEY.startswith("django-insecure-")
):
    raise ImproperlyConfigured(
        "Inject a production SECRET_KEY of at least 50 characters."
    )
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must list explicit API hostnames.")
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured(
        "FRONTEND_ORIGINS must list trusted HTTPS frontend origins."
    )
for origin in CORS_ALLOWED_ORIGINS:
    parts = urlsplit(origin)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or "*" in origin
        or parts.username is not None
        or parts.password is not None
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise ImproperlyConfigured(
            "FRONTEND_ORIGINS entries must be explicit HTTPS origins without paths."
        )
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

database_url = os.getenv("DATABASE_URL", "")
db_parts = urlsplit(database_url)
if (
    db_parts.scheme not in ("postgres", "postgresql")
    or not db_parts.hostname
    or not db_parts.path.lstrip("/")
):
    raise ImproperlyConfigured(
        "DATABASE_URL must identify a PostgreSQL host and database."
    )
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(db_parts.path.lstrip("/")),
        "USER": unquote(db_parts.username or ""),
        "PASSWORD": unquote(db_parts.password or ""),
        "HOST": db_parts.hostname,
        "PORT": str(db_parts.port or 5432),
        "OPTIONS": {
            key: values[-1] for key, values in parse_qs(db_parts.query).items()
        },
    },
}

SESSION_COOKIE_NAME = "__Host-sessionid"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_NAME = "__Host-csrftoken"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "None"

try:
    NUM_PROXIES = int(os.getenv("NUM_PROXIES", "0"))
    if NUM_PROXIES < 0:
        raise ValueError
except ValueError:
    raise ImproperlyConfigured("NUM_PROXIES must be a nonnegative integer.") from None
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
    else None
)
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": os.getenv("EMAIL_HOST", ""),
            "port": int(os.getenv("EMAIL_PORT", "587")),
            "username": os.getenv("EMAIL_HOST_USER", ""),
            "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
            "use_tls": os.getenv("EMAIL_USE_TLS", "true").lower() == "true",
            "use_ssl": os.getenv("EMAIL_USE_SSL", "false").lower() == "true",
            "timeout": 10,
        },
    },
}
if not MAILERS["default"]["OPTIONS"]["host"]:
    raise ImproperlyConfigured("EMAIL_HOST is required in production.")
if (
    MAILERS["default"]["OPTIONS"]["use_tls"]
    and MAILERS["default"]["OPTIONS"]["use_ssl"]
):
    raise ImproperlyConfigured("Choose EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")
if not DEFAULT_FROM_EMAIL:
    raise ImproperlyConfigured("DEFAULT_FROM_EMAIL is required in production.")
