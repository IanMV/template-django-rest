from pathlib import Path

# from django.contrib import messages
from dotenv import load_dotenv

load_dotenv()

# /
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# /

# ABSOLUTE_URL_OVERRIDES = {}
# ADMINS = []
### ALLOWED_HOSTS = []
APPEND_SLASH = True

# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
#         # "KEY_FUNCTION": ,
#         "KEY_PREFIX": "",
#         "LOCATION": "",
#         "OPTIONS": {},
#         "TIMEOUT": 300,
#         "VERSION": 1,
#     }
# }
# CACHE_MIDDLEWARE_ALIAS = "default"
# CACHE_MIDDLEWARE_KEY_PREFIX = ""
# CACHE_MIDDLEWARE_SECONDS = 600

# CSRF_COOKIE_AGE = 31449600  # 1 year in seconds
# CSRF_COOKIE_DOMAIN = None
# CSRF_COOKIE_HTTPONLY = False
# CSRF_COOKIE_NAME = "csrftoken"
# CSRF_COOKIE_PATH = "/"
# CSRF_COOKIE_SAMESITE = "Lax"
# CSRF_COOKIE_SECURE = False
# CSRF_USE_SESSIONS = False
# CSRF_FAILURE_VIEW = "django.views.csrf.csrf_failure"
# CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
# CSRF_TRUSTED_ORIGINS = []

### DATABASES = {}

# DATA_UPLOAD_MAX_MEMORY_SIZE = 2621440
# DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
# DATA_UPLOAD_MAX_NUMBER_FILES = 100
# DATABASE_ROUTERS = []

# DATE_FORMAT = "N j, Y"
# DATE_INPUT_FORMATS = [
#     "%Y-%m-%d",  # '2006-10-25'
#     "%m/%d/%Y",  # '10/25/2006'
#     "%m/%d/%y",  # '10/25/06'
#     "%b %d %Y",  # 'Oct 25 2006'
#     "%b %d, %Y",  # 'Oct 25, 2006'
#     "%d %b %Y",  # '25 Oct 2006'
#     "%d %b, %Y",  # '25 Oct, 2006'
#     "%B %d %Y",  # 'October 25 2006'
#     "%B %d, %Y",  # 'October 25, 2006'
#     "%d %B %Y",  # '25 October 2006'
#     "%d %B, %Y",  # '25 October, 2006'
# ]

### DEBUG
### DEBUG_PROPAGATE_EXCEPTIONS

# DECIMAL_SEPARATOR = "."
# DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# DEFAULT_CHARSET = "utf-8"
# DEFAULT_EXCEPTION_REPORTER = "django.views.debug.ExceptionReporter"
# DEFAULT_EXCEPTION_REPORTER_FILTER = "django.views.debug.SafeExceptionReporterFilter"
# DEFAULT_FROM_EMAIL = "webmaster@localhost"
# DEFAULT_INDEX_TABLESPACE = ""
# DEFAULT_TABLESPACE = ""
# DISALLOWED_USER_AGENTS = []
# EMAIL_BACKEND
# EMAIL_FILE_PATH
# EMAIL_HOST
# EMAIL_HOST_PASSWORD
# EMAIL_HOST_USER
# EMAIL_PORT
# EMAIL_SUBJECT_PREFIX
# EMAIL_USE_LOCALTIME
# EMAIL_USE_TLS
# EMAIL_USE_SSL
# EMAIL_SSL_CERTFILE
# EMAIL_SSL_KEYFILE
# EMAIL_TIMEOUT

# FILE_UPLOAD_HANDLERS = [
#     "django.core.files.uploadhandler.MemoryFileUploadHandler",
#     "django.core.files.uploadhandler.TemporaryFileUploadHandler",
# ]
# FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440
# FILE_UPLOAD_DIRECTORY_PERMISSIONS = None
# FILE_UPLOAD_PERMISSIONS = 0o644
# FILE_UPLOAD_TEMP_DIR = None

# FIRST_DAY_OF_WEEK = 0  # Sunday
# FIXTURE_DIRS = []
# FORCE_SCRIPT_NAME = None
# FORM_RENDERER = "django.forms.renderers.DjangoTemplates"
# FORMAT_MODULE_PATH = None
# IGNORABLE_404_URLS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drf_spectacular",
    "rest_framework",
    "core",
]

# INTERNAL_IPS = []
# LANGUAGE_CODE = "en-us"
# LANGUAGE_COOKIE_AGE = None
# LANGUAGE_COOKIE_DOMAIN = None
# LANGUAGE_COOKIE_HTTPONLY = False
# LANGUAGE_COOKIE_NAME = "django_language"
# LANGUAGE_COOKIE_PATH = "/"
# LANGUAGE_COOKIE_SAMESITE = None
# LANGUAGE_COOKIE_SECURE = False

LANGUAGES = [
    ("en", "English"),
]
LANGUAGES_BIDI = []
# LOCALE_PATHS = []

LOGGING = {}
# LOGGING_CONFIG = "logging.config.dictConfig"

### MAILERS

# MANAGERS = []

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

# MIGRATION_MODULES = {}
# MONTH_DAY_FORMAT = "F j"
# NUMBER_GROUPING = 0
# PREPEND_WWW = False

ROOT_URLCONF = "app.urls"

### SECRET_KEY
### SECRET_KEY_FALLBACKS

# SECURE_CONTENT_TYPE_NOSNIFF = True
# SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
# SECURE_CSP = {}
# SECURE_CSP_REPORT_ONLY = {}
# SECURE_HSTS_INCLUDE_SUBDOMAINS = False
# SECURE_HSTS_PRELOAD = False
# SECURE_HSTS_SECONDS = 0
# SECURE_PROXY_SSL_HEADER = None
# SECURE_REDIRECT_EXEMPT = []
# SECURE_REFERRER_POLICY = "same-origin"
# SECURE_SSL_HOST = None
# SECURE_SSL_REDIRECT = False

# SERIALIZATION_MODULES

# SERVER_EMAIL = "root@localhost"
# SHORT_DATE_FORMAT = "m/d/Y"
# SHORT_DATETIME_FORMAT = "m/d/Y P"
# SIGNED_COOKIE_LEGACY_SALT_FALLBACK = False
# SIGNING_BACKEND = "django.core.signing.TimestampSigner"
# SILENCED_SYSTEM_CHECKS = []

# STORAGES = {
#     "default": {
#         "BACKEND": "django.core.files.storage.FileSystemStorage",
#     },
#     "staticfiles": {
#         "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
#     },
# }

# TASKS = {
#     "default": {
#         "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
#         # QUEUES
#         # OPTIONS
#     }
# }

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

# TEST_RUNNER = "django.test.runner.DiscoverRunner"
# TEST_NON_SERIALIZED_APPS = []
# THOUSAND_SEPARATOR = ","
# TIME_FORMAT = "P"
# TIME_INPUT_FORMATS = [
#     "%H:%M:%S",  # '14:30:59'
#     "%H:%M:%S.%f",  # '14:30:59.000200'
#     "%H:%M",  # '14:30'
# ]

TIME_ZONE = "America/Sao_Paulo"

# USE_BLANK_CHOICE_DASH = False
# USE_I18N = True
# USE_THOUSAND_SEPARATOR = False
# USE_TZ = True
# USE_X_FORWARDED_HOST = False
# USE_X_FORWARDED_PORT = False
# URLIZE_ASSUME_HTTPS = False # Decraptaded in 6.1

WSGI_APPLICATION = "app.wsgi.application"

# YEAR_MONTH_FORMAT = "F Y"
# X_FRAME_OPTIONS = "DENY"

# AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
AUTH_USER_MODEL = "core.User"

# LOGIN_REDIRECT_URL = "/accounts/profile/"
# LOGIN_URL = "/accounts/login/"
# LOGOUT_REDIRECT_URL = None
# PASSWORD_RESET_TIMEOUT = 259200

# PASSWORD_HASHERS = [
#     "django.contrib.auth.hashers.PBKDF2PasswordHasher",
#     "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
#     "django.contrib.auth.hashers.Argon2PasswordHasher",
#     "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
#     "django.contrib.auth.hashers.ScryptPasswordHasher",
# ]

# AUTH_PASSWORD_VALIDATORS = [
#     {
#         "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
#     },
#     {
#         "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
#         "OPTIONS": {
#             "min_length": 9,
#         },
#     },
#     {
#         "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
#     },
#     {
#         "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
#     },
# ]

# MESSAGE_LEVEL = messages.INFO
# MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
# MESSAGE_TAGS = {
#     messages.DEBUG: "debug",
#     messages.INFO: "info",
#     messages.SUCCESS: "success",
#     messages.WARNING: "warning",
#     messages.ERROR: "error",
# }

# SESSION_CACHE_ALIAS = "default"
# SESSION_COOKIE_AGE = 1209600  # 2 weeks in seconds
# SESSION_COOKIE_DOMAIN = None
# SESSION_COOKIE_HTTPONLY = True
# SESSION_COOKIE_NAME = "sessionid"
# SESSION_COOKIE_PATH = "/"
# SESSION_COOKIE_SAMESITE = "Lax"
# SESSION_COOKIE_SECURE = False
# SESSION_ENGINE = "django.contrib.sessions.backends.db"
# SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# SESSION_FILE_PATH = None
# SESSION_SAVE_EVERY_REQUEST = False
# SESSION_SERIALIZER = "django.contrib.sessions.serializers.JSONSerializer"

# SITE_ID
# STATIC_ROOT = None

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_FINDERS = []

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
