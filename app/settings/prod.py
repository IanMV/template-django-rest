import os
from urllib.parse import parse_qs, urlsplit, urlunsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
NUM_PROXIES = int(os.getenv("NUM_PROXIES", "0"))
SIMPLE_JWT = {**SIMPLE_JWT, "AUTH_COOKIE_SECURE": True}  # noqa: F405
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SECRET_KEY = os.getenv("SECRET_KEY")
redis_url = os.getenv("REDIS_URL")
if not redis_url:
    raise ImproperlyConfigured("REDIS_URL is required in production.")
redis_parts = urlsplit(redis_url)
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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DATABASE_NAME", str(BASE_DIR / "db.sqlite3")),  # noqa: F405
    }
}
