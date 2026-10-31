from celery import Celery
from django.conf import settings

# A worker must be started with an explicit DJANGO_SETTINGS_MODULE.
settings.INSTALLED_APPS

app = Celery("app")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
