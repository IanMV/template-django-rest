from .prod import *  # noqa: F403

# Production data services, development HTTP/cookies; never deploy publicly.
DEBUG = True
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_PROXY_SSL_HEADER = None
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SIMPLE_JWT = {**SIMPLE_JWT, "AUTH_COOKIE_SECURE": False}  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = False
