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
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
DEFAULT_FROM_EMAIL = "noreply@localhost"
