import hashlib
from unittest.mock import patch

from django.core.cache import cache

from tests.base import ApiCase


class CodeRequestRateLimitTests(ApiCase):
    def test_issuance_email_cache_failure_returns_503(self):
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    "/api/password-reset/request/",
                    {"email": "missing@example.com"},
                    format="json",
                )
        self.assertEqual(response.status_code, 503)

    def test_issuance_ip_cache_failure_fails_open(self):
        with patch(
            "core.auth.rate_limit.cache.add", side_effect=[True, RuntimeError("down")]
        ):
            with self.assertLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    "/api/password-reset/request/",
                    {"email": "missing@example.com"},
                    format="json",
                )
        self.assertEqual(response.status_code, 200)

    def test_same_scope_and_email_is_throttled_even_from_another_ip(self):
        email = "missing@example.com"
        first = self.client.post(
            "/api/password-reset/request/",
            {"email": email},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        second = self.client.post(
            "/api/password-reset/request/",
            {"email": email},
            format="json",
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual((first.status_code, second.status_code), (200, 429))

    def test_same_scope_and_ip_throttles_different_emails(self):
        first = self.client.post(
            "/api/password-reset/request/",
            {"email": "first@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        second = self.client.post(
            "/api/password-reset/request/",
            {"email": "second@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual((first.status_code, second.status_code), (200, 429))

    def test_scopes_have_independent_cooldowns(self):
        email = "new@example.com"
        registration = self.client.post(
            "/api/registration/request/", {"email": email}, format="json"
        )
        reset = self.client.post(
            "/api/password-reset/request/", {"email": email}, format="json"
        )
        self.assertEqual((registration.status_code, reset.status_code), (201, 200))

    def test_remote_addr_is_used_instead_of_forwarded_header(self):
        first = self.client.post(
            "/api/password-reset/request/",
            {"email": "first@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )
        blocked = self.client.post(
            "/api/password-reset/request/",
            {"email": "second@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="8.8.8.8",
        )
        allowed = self.client.post(
            "/api/password-reset/request/",
            {"email": "third@example.com"},
            format="json",
            REMOTE_ADDR="127.0.0.2",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )
        self.assertEqual(
            (first.status_code, blocked.status_code, allowed.status_code),
            (200, 429, 200),
        )


class LoginRateLimitTests(ApiCase):
    def setUp(self):
        super().setUp()
        self.client.get("/api/login/")
        self.client.credentials(HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

    def attempt(self, email, ip):
        return self.client.post(
            "/api/login/",
            {"email": email, "password": "wrong"},
            format="json",
            REMOTE_ADDR=ip,
        )

    def test_same_email_from_different_ips_does_not_lock_account(self):
        user = self.create_user()
        for attempt in range(10):
            self.assertEqual(
                self.attempt(user.email, f"127.0.0.{attempt + 1}").status_code, 401
            )
        self.assertEqual(self.attempt(user.email, "127.0.0.11").status_code, 401)

    def test_eleventh_login_for_same_ip_and_email_is_throttled(self):
        user = self.create_user()
        for _ in range(10):
            self.assertEqual(self.attempt(user.email, "127.0.0.1").status_code, 401)
        self.assertEqual(self.attempt(user.email, "127.0.0.1").status_code, 429)

    def test_successful_login_resets_pair_limit(self):
        user = self.create_user()
        for _ in range(9):
            self.assertEqual(self.attempt(user.email, "127.0.0.1").status_code, 401)
        self.login(user)
        for _ in range(10):
            self.assertEqual(self.attempt(user.email, "127.0.0.1").status_code, 401)
        self.assertEqual(self.attempt(user.email, "127.0.0.1").status_code, 429)

    def test_thirty_first_login_for_same_ip_is_throttled(self):
        ip_digest = hashlib.sha256(b"127.0.0.1").hexdigest()
        cache.set(f"login:ip:{ip_digest}", 29, timeout=300)
        self.assertEqual(self.attempt("person29@example.com", "127.0.0.1").status_code, 401)
        self.assertEqual(
            self.attempt("person30@example.com", "127.0.0.1").status_code, 429
        )

    def test_login_cache_failure_fails_open(self):
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.rate_limit", level="ERROR"):
                response = self.attempt("missing@example.com", "127.0.0.1")
        self.assertEqual(response.status_code, 401)


class CodeVerificationRateLimitTests(ApiCase):
    def test_sixteenth_attempt_and_confirmation_share_ip_throttle(self):
        for _ in range(15):
            response = self.client.post(
                "/api/registration/verify/",
                {"email": "missing@example.com", "code": "000000"},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/registration/confirm/",
            {
                "email": "missing@example.com",
                "code": "000000",
                "name": "Example Person",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 429)

    def test_verification_cache_failure_fails_closed(self):
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    "/api/registration/verify/",
                    {"email": "missing@example.com", "code": "000000"},
                    format="json",
                )
        self.assertEqual(response.status_code, 503)
