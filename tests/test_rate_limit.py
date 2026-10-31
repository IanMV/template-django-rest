import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.core.cache import cache
from rest_framework import serializers
from rest_framework.exceptions import Throttled

from core.auth.rate_limit import require_current_password
from core.shared.exceptions import ServiceUnavailable
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
            "core.auth.rate_limit.cache.add", side_effect=[RuntimeError("down"), True]
        ):
            with self.assertLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    "/api/password-reset/request/",
                    {"email": "missing@example.com"},
                    format="json",
                )
        self.assertEqual(response.status_code, 200)

    def test_ip_burst_throttle_does_not_consume_email_cooldown(self):
        email = "burst@example.com"
        # Seed IP burst throttle (ip key timeout 2s)
        ip_digest = hashlib.sha256(b"127.0.0.1").hexdigest()
        cache.set(f"code-request:password-reset:ip:{ip_digest}", True, timeout=2)

        # Request fails on IP throttle
        blocked = self.client.post(
            "/api/password-reset/request/",
            {"email": email},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(blocked.status_code, 429)

        # Clear IP burst throttle to simulate waiting 2s
        cache.delete(f"code-request:password-reset:ip:{ip_digest}")

        # Retry should succeed because email cooldown was NOT consumed by the blocked attempt
        allowed = self.client.post(
            "/api/password-reset/request/",
            {"email": email},
            format="json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(allowed.status_code, 200)

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


class ReauthenticationRateLimitTests(ApiCase):
    def test_reauth_atomic_throttle_under_concurrent_failures(self):
        user = self.create_user()
        user_digest = hashlib.sha256(str(user.pk).encode()).hexdigest()
        key = f"reauth:user:{user_digest}"
        cache.set(key, 4, timeout=300)

        results = []
        barrier = Barrier(5)

        def check_password(_password):
            barrier.wait(timeout=5)
            return False

        def worker():
            try:
                require_current_password(user, "wrong-password")
                results.append("ok")
            except serializers.ValidationError:
                results.append("400")
            except Throttled:
                results.append("429")

        with patch.object(user, "check_password", side_effect=check_password):
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(worker) for _ in range(5)]
                for future in futures:
                    future.result()

        self.assertEqual(sorted(results), ["400", "429", "429", "429", "429"])
        self.assertEqual(cache.get(key), 9)

    def test_reauth_subsequent_attempts_throttled_before_password_check(self):
        user = self.create_user()
        user_digest = hashlib.sha256(str(user.pk).encode()).hexdigest()
        key = f"reauth:user:{user_digest}"
        cache.set(key, 5, timeout=300)

        with patch.object(user, "check_password") as mock_check:
            with self.assertRaises(Throttled):
                require_current_password(user, self.password)
            mock_check.assert_not_called()

    def test_reauth_success_resets_counter(self):
        user = self.create_user()
        user_digest = hashlib.sha256(str(user.pk).encode()).hexdigest()
        key = f"reauth:user:{user_digest}"
        with self.assertRaises(serializers.ValidationError):
            require_current_password(user, "wrong-password")
        self.assertEqual(cache.get(key), 1)

        require_current_password(user, self.password)
        self.assertIsNone(cache.get(key))

    def test_reauth_cache_failure_during_increment_fails_closed(self):
        user = self.create_user()
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            with self.assertLogs("core.auth.rate_limit", level="ERROR"):
                with self.assertRaises(ServiceUnavailable):
                    require_current_password(user, "wrong-password")
