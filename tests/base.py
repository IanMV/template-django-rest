import re

from django.core import mail
from django.core.cache import caches
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from core.models.user import User


class BehaviorHelpers:
    password = "StrongPass!4693$"

    def setUp(self):
        super().setUp()
        caches["default"].clear()
        mail.outbox.clear()
        self.client = self.new_client()
        self.bootstrap(self.client)

    def bootstrap(self, client):
        response = client.get("/api/login/")
        self.assertEqual(response.status_code, 200)
        client.credentials(HTTP_X_CSRFTOKEN=response.data["csrfToken"])
        return response

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
        self, user, client=None, password=None, ip="127.0.0.1", agent="TestBrowser"
    ):
        client = client or self.client
        self.bootstrap(client)
        payload = {"email": user.email, "password": password or self.password}
        response = client.post(
            "/api/login/",
            payload,
            format="json",
            REMOTE_ADDR=ip,
            HTTP_USER_AGENT=agent,
        )
        self.assertEqual(response.status_code, 200, response.data)
        client.credentials(HTTP_X_CSRFTOKEN=response.data["csrfToken"])
        return client, response

    def email_code(self):
        self.assertTrue(mail.outbox)
        code = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[-1].body)
        self.assertIsNotNone(code)
        return code.group()

    def post_with_commit(self, path, data, **extra):
        if isinstance(self, TestCase):
            with self.captureOnCommitCallbacks(execute=True):
                return self.client.post(path, data, format="json", **extra)
        return self.client.post(path, data, format="json", **extra)


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SECRET_KEY="django-insecure-test-key-with-strictly-more-than-thirty-two-bytes-12345",
)
class ApiCase(BehaviorHelpers, TestCase):
    pass


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SECRET_KEY="django-insecure-test-key-with-strictly-more-than-thirty-two-bytes-12345",
)
class ApiTransactionCase(BehaviorHelpers, TransactionTestCase):
    pass
