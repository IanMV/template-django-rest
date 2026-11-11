import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def _env_bool(name, default):
    value = (os.getenv(name, default) or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ImproperlyConfigured(f"{name} must be 'true' or 'false'.")


def _env_port(name, default="587"):
    try:
        port = int(os.getenv(name, default))
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        raise ImproperlyConfigured(
            f"{name} must be an integer between 1 and 65535."
        ) from None
    return port


DEBUG = True
SECRET_KEY = "django-insecure-local-development-only-not-for-public-use"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    },
}
MAILERS = {
    "default": {
        "BACKEND": os.getenv(
            "EMAIL_BACKEND",
            "django.core.mail.backends.console.EmailBackend",
        ),
    }
}
if MAILERS["default"]["BACKEND"] == "django.core.mail.backends.smtp.EmailBackend":
    MAILERS["default"]["OPTIONS"] = {
        "host": os.getenv("EMAIL_HOST", "").strip(),
        "port": _env_port("EMAIL_PORT", "587"),
        "username": os.getenv("EMAIL_HOST_USER", ""),
        "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
        "use_tls": _env_bool("EMAIL_USE_TLS", "true"),
        "use_ssl": _env_bool("EMAIL_USE_SSL", "false"),
        "timeout": 10,
    }
    if not MAILERS["default"]["OPTIONS"]["host"]:
        raise ImproperlyConfigured("EMAIL_HOST is required when using SMTP.")
    if (
        MAILERS["default"]["OPTIONS"]["use_tls"]
        and MAILERS["default"]["OPTIONS"]["use_ssl"]
    ):
        raise ImproperlyConfigured("Choose EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
DEFAULT_FROM_EMAIL = (
    os.getenv("DEFAULT_FROM_EMAIL") or ""
).strip() or "noreply@localhost"
