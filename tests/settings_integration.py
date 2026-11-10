from .settings import *  # noqa: F403

# Synthetic, disposable PostgreSQL service used by CI, never a production database.
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
