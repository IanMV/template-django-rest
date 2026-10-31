import os

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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DATABASE_NAME", str(BASE_DIR / "db.sqlite3")),  # noqa: F405
    }
}
