from unittest.mock import patch

from django.core.cache import cache
from rest_framework import serializers
from rest_framework.exceptions import Throttled

from core.auth.rate_limit import _key, require_current_password
from core.shared.exceptions import ServiceUnavailable
from tests.base import ApiCase


class CodeRequestRateLimitTests(ApiCase):
    def request(
        self, email="missing@example.com", ip="127.0.0.1", flow="password-reset"
    ):
        return self.client.post(
            f"/api/{flow}/request/", {"email": email}, format="json", REMOTE_ADDR=ip
        )

    def test_ip_cache_failure_fails_closed(self):
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            self.assertEqual(self.request().status_code, 503)

    def test_email_cache_failure_fails_closed(self):
        with patch(
            "core.auth.rate_limit.cache.add", side_effect=[True, RuntimeError("down")]
        ):
            self.assertEqual(self.request().status_code, 503)

    def test_blocked_ip_does_not_consume_email_cooldown(self):
        key = _key("password-reset:ip", "127.0.0.1")
        cache.set(key, 1, 2)
        self.assertEqual(self.request().status_code, 429)
        cache.delete(key)
        self.assertEqual(self.request().status_code, 200)

    def test_email_is_limited_across_ips_and_case_variants(self):
        self.assertEqual(self.request().status_code, 200)
        response = self.request("MISSING@EXAMPLE.COM", "127.0.0.2")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_same_ip_limits_different_emails(self):
        self.assertEqual(self.request().status_code, 200)
        self.assertEqual(self.request("second@example.com").status_code, 429)

    def test_scopes_have_independent_cooldowns(self):
        self.assertEqual(self.request(flow="registration").status_code, 201)
        self.assertEqual(self.request().status_code, 200)

    def test_forwarded_header_cannot_bypass_limits(self):
        self.assertEqual(self.request().status_code, 200)
        response = self.client.post(
            "/api/password-reset/request/",
            {"email": "second@example.com"},
            format="json",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )
        self.assertEqual(response.status_code, 429)


class LoginRateLimitTests(ApiCase):
    def test_successful_logins_do_not_spend_shared_ip_budget(self):
        user = self.create_user()
        cache.set(_key("login:ip", "127.0.0.1"), 29, 300)
        for _ in range(31):
            self.login(user)
        self.assertEqual(cache.get(_key("login:ip", "127.0.0.1")), 29)

    def test_blocked_pair_does_not_spend_shared_ip_budget(self):
        from core.auth.rate_limit import login_pair_key

        cache.set(login_pair_key("missing@example.com", "127.0.0.1"), 10, 300)
        for _ in range(31):
            self.assertEqual(self.attempt().status_code, 429)
        self.assertIsNone(cache.get(_key("login:ip", "127.0.0.1")))

    def test_exhausted_ip_is_checked_before_authentication(self):
        cache.set(_key("login:ip", "127.0.0.1"), 30, 300)
        with patch("core.auth.services.authenticate") as authenticate:
            self.assertEqual(self.attempt().status_code, 429)
        authenticate.assert_not_called()

    def attempt(self, email="missing@example.com", ip="127.0.0.1"):
        return self.client.post(
            "/api/login/",
            {"email": email, "password": "wrong"},
            format="json",
            REMOTE_ADDR=ip,
        )

    def test_same_email_from_different_ips_does_not_lock_account(self):
        for attempt in range(11):
            self.assertEqual(self.attempt(ip=f"127.0.0.{attempt + 1}").status_code, 401)

    def test_eleventh_attempt_is_throttled(self):
        for _ in range(10):
            self.assertEqual(self.attempt().status_code, 401)
        self.assertEqual(self.attempt().status_code, 429)

    def test_successful_login_resets_pair_limit(self):
        user = self.create_user()
        for _ in range(9):
            self.assertEqual(self.attempt(user.email).status_code, 401)
        self.login(user)
        for _ in range(10):
            self.assertEqual(self.attempt(user.email).status_code, 401)
        self.assertEqual(self.attempt(user.email).status_code, 429)

    def test_thirty_first_login_for_ip_is_throttled(self):
        cache.set(_key("login:ip", "127.0.0.1"), 29, 300)
        self.assertEqual(self.attempt("first@example.com").status_code, 401)
        self.assertEqual(self.attempt("second@example.com").status_code, 429)

    def test_login_cache_failure_fails_closed(self):
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            self.assertEqual(self.attempt().status_code, 503)

    def test_login_counter_reset_failure_returns_unavailable(self):
        user = self.create_user()
        with patch(
            "core.auth.rate_limit.cache.delete", side_effect=RuntimeError("down")
        ):
            response = self.client.post(
                "/api/login/",
                {"email": user.email, "password": self.password},
                format="json",
            )
        self.assertEqual(response.status_code, 503)

        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)


class CodeConfirmationRateLimitTests(ApiCase):
    def confirm(self):
        return self.client.post(
            "/api/registration/confirm/",
            {
                "email": "missing@example.com",
                "code": "000000",
                "name": "Example Person",
                "password": self.password,
            },
            format="json",
        )

    def test_sixteenth_confirmation_is_throttled(self):
        for _ in range(15):
            self.assertEqual(self.confirm().status_code, 400)
        self.assertEqual(self.confirm().status_code, 429)

    def test_cache_failure_fails_closed(self):
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            self.assertEqual(self.confirm().status_code, 503)


class ReauthenticationRateLimitTests(ApiCase):
    def test_exhausted_budget_does_not_run_more_password_checks(self):
        user = self.create_user()
        key = _key("reauth:user", user.pk)
        cache.set(key, 4, 300)
        with patch.object(user, "check_password", return_value=False) as check:
            with self.assertRaises(serializers.ValidationError):
                require_current_password(user, "wrong")
            for _ in range(4):
                with self.assertRaises(Throttled):
                    require_current_password(user, "wrong")
        self.assertEqual(check.call_count, 1)
        self.assertEqual(cache.get(key), 5)

    def test_blocked_attempt_does_not_check_password(self):
        user = self.create_user()
        cache.set(_key("reauth:user", user.pk), 5, 300)
        with patch.object(user, "check_password") as check:
            with self.assertRaises(Throttled):
                require_current_password(user, self.password)
            check.assert_not_called()

    def test_success_resets_counter(self):
        user = self.create_user()
        key = _key("reauth:user", user.pk)
        with self.assertRaises(serializers.ValidationError):
            require_current_password(user, "wrong")
        self.assertEqual(cache.get(key), 1)
        require_current_password(user, self.password)
        self.assertIsNone(cache.get(key))

    def test_increment_failure_fails_closed(self):
        user = self.create_user()
        with patch("core.auth.rate_limit.cache.add", side_effect=RuntimeError("down")):
            with self.assertRaises(ServiceUnavailable):
                require_current_password(user, "wrong")
