from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NUM_PROXIES = 0
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "drf_spectacular",
    "rest_framework",
    "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "app.urls"
WSGI_APPLICATION = "app.wsgi.application"
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
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Sao_Paulo"
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "name")},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 9},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 24 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"^/api/.*$"
CACHES = {
    # shortcut: limits are per process and reset on restart; use shared storage for global enforcement.
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.auth.authenticate.CustomAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Authentication API",
    "VERSION": "2.0.0",
    "DESCRIPTION": (
        "Call GET /api/login/ with credentials to obtain csrfToken. Send it as "
        "X-CSRFTOKEN on mutations. Login sets an HttpOnly session cookie valid for "
        "24 hours and returns a rotated csrfToken. Never copy the session cookie "
        "into JavaScript. Cross-site cookies depend on browser policy."
    ),
    "COMPONENT_SPLIT_REQUEST": True,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "AUTHENTICATION_WHITELIST": ["core.auth.authenticate.CustomAuthentication"],
    "SWAGGER_UI_SETTINGS": """{
        deepLinking: true,
        persistAuthorization: false,
        requestInterceptor: async (request) => {
            if (new URL(request.url, location.href).origin !== location.origin) return request;
            request.credentials = 'same-origin';
            if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
                const response = await fetch('/api/login/', {
                    credentials: 'same-origin', cache: 'no-store'
                });
                if (!response.ok) throw new Error('CSRF bootstrap failed');
                request.headers['X-CSRFTOKEN'] = (await response.json()).csrfToken;
            }
            return request;
        }
    }""",
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"core": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
