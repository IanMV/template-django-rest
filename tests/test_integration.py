import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import connection, connections
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, Throttled

from core.auth.rate_limit import require_current_password
from core.auth.services import AuthService, SessionService
from core.models import UserSession
from tests.base import ApiTransactionCase


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL/Redis settings")
class ProductionConcurrencyTests(ApiTransactionCase):
    def concurrent(self, operation, count=2):
        def worker():
            try:
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(worker) for _ in range(count)]
            return [future.result(timeout=20) for future in futures]

    def test_matching_device_logins_leave_one_active_session(self):
        user = self.create_user()
        ready = Barrier(2)

        def authenticated(**credentials):
            result = authenticate(**credentials)
            ready.wait(timeout=10)
            return result

        with patch("core.auth.services.authenticate", side_effect=authenticated):
            results = self.concurrent(
                lambda: AuthService.login_user(
                    user.email, self.password, "TestBrowser", "127.0.0.1"
                )
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(
            UserSession.objects.filter(user=user, is_active=True).count(), 1
        )

    def test_concurrent_refresh_reuse_revokes_rotated_session(self):
        user = self.create_user()
        self.login(user)
        raw = self.client.cookies["refresh_token"].value
        ready = Barrier(2)
        rotate = SessionService._rotate_refresh

        def synchronized(*args):
            ready.wait(timeout=10)
            return rotate(*args)

        def refresh():
            from rest_framework_simplejwt.serializers import TokenRefreshSerializer

            try:
                SessionService.refresh_tokens(raw, TokenRefreshSerializer)
            except AuthenticationFailed:
                return 401
            return 200

        with patch.object(SessionService, "_rotate_refresh", side_effect=synchronized):
            self.assertEqual(sorted(self.concurrent(refresh)), [200, 401])
        self.assertFalse(UserSession.objects.get(user=user).is_active)

    def test_redis_reauthentication_counter_limits_concurrent_failures(self):
        user = self.create_user()
        key = f"reauth:user:{hashlib.sha256(str(user.pk).encode()).hexdigest()}"
        cache.set(key, 4, timeout=300)
        ready = Barrier(5)

        def wrong_password(_password):
            ready.wait(timeout=10)
            return False

        def reauthenticate():
            try:
                require_current_password(user, "wrong")
            except Throttled:
                return 429
            except serializers.ValidationError:
                return 400
            return 200

        with patch.object(user, "check_password", side_effect=wrong_password):
            self.assertEqual(
                sorted(self.concurrent(reauthenticate, 5)), [400] + [429] * 4
            )
        self.assertEqual(cache.get(key), 9)
