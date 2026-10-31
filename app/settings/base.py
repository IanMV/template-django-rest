from datetime import timedelta
from pathlib import Path

# from django.contrib import messages


BASE_DIR = Path(__file__).resolve().parent.parent.parent
NUM_PROXIES = 0
SESSION_CACHE_TTL = 60
SESSION_ABSOLUTE_LIFETIME = timedelta(days=30)
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "sessions": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sessions",
        "KEY_PREFIX": "sessions",
    },
}
APPEND_SLASH = True
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
]
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_SAMESITE = "Lax"
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drf_spectacular",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "core",
]
LANGUAGES = [
    ("en", "English"),
]
LANGUAGES_BIDI = []
LOGGING = {}
STATIC_URL = "static/"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "app.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
TIME_ZONE = "America/Sao_Paulo"
WSGI_APPLICATION = "app.wsgi.application"
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "name")},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 9,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.auth.authenticate.CustomAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "CHECK_REVOKE_TOKEN": True,
    "CHECK_USER_IS_ACTIVE": True,
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_DOMAIN": None,
    "AUTH_COOKIE_SECURE": False,
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_PATH": "/",
    "AUTH_COOKIE_SAMESITE": "Lax",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Authentication API",
    "DESCRIPTION": (
        "Use the Swagger UI on the same origin as the API. Start with GET /api/login/ "
        "to receive the CSRF cookie; POST /api/login/ with credentials to receive "
        "HttpOnly access/refresh cookies. The browser sends cookies automatically; "
        "send the csrftoken value in X-CSRFTOKEN for unsafe requests. Swagger UI "
        "injects the CSRF header for same-origin requests. Do not paste HttpOnly "
        "JWTs into Authorize: authenticate through the login operation instead."
    ),
    "VERSION": "1.0.0",
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "auth", "description": "CSRF bootstrap, login, refresh and logout."},
        {"name": "sessions", "description": "List and deactivate device sessions."},
        {
            "name": "registration",
            "description": "Request, verify and confirm registration.",
        },
        {
            "name": "password-reset",
            "description": "Request, verify and confirm password reset.",
        },
        {
            "name": "email-change",
            "description": "Request, verify and confirm an email change.",
        },
        {"name": "user", "description": "Current account and user list."},
    ],
    "AUTHENTICATION_WHITELIST": [
        "core.auth.authenticate.CustomAuthentication",
    ],
}
