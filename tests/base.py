import re

from django.core import mail
from django.core.cache import cache, caches
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from core.models.user import User


class BehaviorHelpers:
    password = "StrongPass!4693$"

    def setUp(self):
        super().setUp()
        cache.clear()
        caches["sessions"].clear()
        mail.outbox.clear()
        self.client = self.new_client()

    def new_client(self):
        return APIClient(enforce_csrf_checks=True)

    def create_user(self, email="person@example.com", password=None, **fields):
        return User.objects.create_user(
            email=email,
            password=password or self.password,
            name="Example Person",
            **fields,
        )

    def login(
        self, user, client=None, password=None, ip="127.0.0.1", agent="TestBrowser", remember_me=False
    ):
        client = client or self.client
        bootstrap = client.get("/api/login/", REMOTE_ADDR=ip)
        self.assertEqual(bootstrap.status_code, 204)
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        payload = {"email": user.email, "password": password or self.password}
        if remember_me:
            payload["remember_me"] = True
        response = client.post(
            "/api/login/",
            payload,
            format="json",
            REMOTE_ADDR=ip,
            HTTP_USER_AGENT=agent,
        )
        self.assertEqual(response.status_code, 200, response.data)
        return client, response

    def email_code(self):
        self.assertTrue(mail.outbox)
        code = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[-1].body)
        self.assertIsNotNone(code)
        return code.group()

    def post_with_commit(self, path, data):
        if isinstance(self, TestCase):
            with self.captureOnCommitCallbacks(execute=True):
                return self.client.post(path, data, format="json")
        return self.client.post(path, data, format="json")


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SECRET_KEY="django-insecure-test-key-with-strictly-more-than-thirty-two-bytes-12345",
)
class ApiCase(BehaviorHelpers, TestCase):
    pass


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SECRET_KEY="django-insecure-test-key-with-strictly-more-than-thirty-two-bytes-12345",
)
class ApiTransactionCase(BehaviorHelpers, TransactionTestCase):
    pass
