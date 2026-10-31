import os

from dotenv import load_dotenv

from .base import *  # noqa: F403

load_dotenv(BASE_DIR / ".env")  # noqa: F405

DEBUG = True
DEBUG_PROPAGATE_EXCEPTIONS = False
ALLOWED_HOSTS = []
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-dev-fallback-secret-key-with-at-least-thirty-two-bytes-12345",
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        "TIME_ZONE": "UTC",
    }
}
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
