from uuid import uuid4

from app.settings.base import *  # noqa: F403

SECRET_KEY = "integration-test-only-secret-key-at-least-thirty-two-bytes"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test",
        "USER": "postgres",
        "PASSWORD": "test",
        "HOST": "127.0.0.1",
        "PORT": "5432",
        "OPTIONS": {
            "connect_timeout": 5,
            "options": "-c lock_timeout=5000 -c statement_timeout=15000",
        },
        "TEST": {"NAME": "test_template_auth_integration"},
    }
}
CACHES = {
    alias: {
        "BACKEND": "tests.redis_cache.TestRedisCache",
        "LOCATION": "redis://127.0.0.1:6379/0",
        "KEY_PREFIX": f"template-auth-test:{uuid4().hex}:{alias}",
        "OPTIONS": {"socket_connect_timeout": 5, "socket_timeout": 5},
    }
    for alias in ("default", "sessions")
}
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
