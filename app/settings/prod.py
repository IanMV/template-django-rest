import os
import ssl
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
retention = os.getenv("AUDIT_RETENTION_DAYS")
if retention is not None:
    try:
        AUDIT_RETENTION_DAYS = int(retention)
        if AUDIT_RETENTION_DAYS <= 0:
            raise ValueError
    except ValueError as exc:
        raise ImproperlyConfigured("AUDIT_RETENTION_DAYS must be a positive integer.") from exc
try:
    NUM_PROXIES = int(os.getenv("NUM_PROXIES", "0"))
    if NUM_PROXIES < 0:
        raise ValueError
except ValueError as exc:
    raise ImproperlyConfigured("NUM_PROXIES must be a nonnegative integer.") from exc
SIMPLE_JWT = {**SIMPLE_JWT, "AUTH_COOKIE_SECURE": True}  # noqa: F405
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS is required in production.")
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS is required in production.")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or not SECRET_KEY.strip():
    raise ImproperlyConfigured("SECRET_KEY is required in production.")
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ImproperlyConfigured("DATABASE_URL is required in production.")
db_parts = urlsplit(database_url)
if db_parts.scheme not in ("postgres", "postgresql"):
    raise ImproperlyConfigured(
        "Production requires a PostgreSQL database supporting row-level locking."
    )
db_name = unquote(db_parts.path.lstrip("/"))
if not db_name:
    raise ImproperlyConfigured("DATABASE_URL must include a database name in its path.")

db_options = {k: v[0] for k, v in parse_qs(db_parts.query).items() if v}
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": unquote(db_parts.username or ""),
        "PASSWORD": unquote(db_parts.password or ""),
        "HOST": db_parts.hostname or "",
        "PORT": str(db_parts.port) if db_parts.port else "5432",
    }
}
if db_options:
    DATABASES["default"]["OPTIONS"] = db_options

redis_url = os.getenv("REDIS_URL")
if not redis_url:
    raise ImproperlyConfigured("REDIS_URL is required in production.")
redis_parts = urlsplit(redis_url)
if redis_parts.scheme not in ("redis", "rediss") or not redis_parts.hostname:
    raise ImproperlyConfigured("REDIS_URL must be a redis:// or rediss:// URL with a host.")
if redis_parts.scheme == "rediss" and (
    not redis_parts.password or "ssl_cert_reqs" in parse_qs(redis_parts.query)
):
    raise ImproperlyConfigured("rediss:// requires credentials and verified TLS.")
if "db" in parse_qs(redis_parts.query, keep_blank_values=True):
    raise ImproperlyConfigured("Specify the Redis DB index in REDIS_URL's path.")
try:
    redis_db = int(redis_parts.path.lstrip("/") or "0")
    if redis_db < 0:
        raise ValueError
except ValueError as exc:
    raise ImproperlyConfigured("REDIS_URL must have a nonnegative DB index.") from exc

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": redis_url,
    },
    "sessions": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": urlunsplit(redis_parts._replace(path=f"/{redis_db + 1}")),
        "KEY_PREFIX": "sessions",
    },
}
CELERY_BROKER_URL = urlunsplit(redis_parts._replace(path=f"/{redis_db + 2}"))
CELERY_BROKER_USE_SSL = (
    {"ssl_cert_reqs": ssl.CERT_REQUIRED} if redis_parts.scheme == "rediss" else None
)

MAILERS = {
    "default": {
        "BACKEND": os.getenv(
            "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
        ),
        "OPTIONS": {
            "host": os.getenv("EMAIL_HOST", "localhost"),
            "port": int(os.getenv("EMAIL_PORT", "587")),
            "username": os.getenv("EMAIL_HOST_USER", ""),
            "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
            "use_tls": os.getenv("EMAIL_USE_TLS", "True").lower() == "true",
            "timeout": 10,
        },
    }
}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")

SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False").lower() == "true"
)
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
