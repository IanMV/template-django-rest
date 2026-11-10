import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

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
        "host": os.getenv("EMAIL_HOST", ""),
        "port": int(os.getenv("EMAIL_PORT", "587")),
        "username": os.getenv("EMAIL_HOST_USER", ""),
        "password": os.getenv("EMAIL_HOST_PASSWORD", ""),
        "use_tls": os.getenv("EMAIL_USE_TLS", "true").lower() == "true",
        "use_ssl": os.getenv("EMAIL_USE_SSL", "false").lower() == "true",
        "timeout": 10,
    }
    if not MAILERS["default"]["OPTIONS"]["host"]:
        raise ImproperlyConfigured("EMAIL_HOST is required when using SMTP.")
    if (
        MAILERS["default"]["OPTIONS"]["use_tls"]
        and MAILERS["default"]["OPTIONS"]["use_ssl"]
    ):
        raise ImproperlyConfigured("Choose EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@localhost")
