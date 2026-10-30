from tests.base import ApiCase


class CodeRequestRateLimitTests(ApiCase):
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

    def test_eleventh_login_for_same_email_is_throttled(self):
        user = self.create_user()
        for attempt in range(10):
            self.assertEqual(
                self.attempt(user.email, f"127.0.0.{attempt + 1}").status_code, 401
            )
        self.assertEqual(self.attempt(user.email, "127.0.0.11").status_code, 429)

    def test_thirty_first_login_for_same_ip_is_throttled(self):
        for attempt in range(30):
            self.assertEqual(
                self.attempt(f"person{attempt}@example.com", "127.0.0.1").status_code,
                401,
            )
        self.assertEqual(
            self.attempt("person30@example.com", "127.0.0.1").status_code, 429
        )
