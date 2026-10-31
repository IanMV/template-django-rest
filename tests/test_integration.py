import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import connection, connections
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, Throttled

from core.auth.rate_limit import require_current_password
from core.auth.services import AuthService, SessionService
from core.email_change.services import EmailChangeService
from core.models import EmailChange, EmailVerification, PasswordReset, User, UserSession
from core.password_reset.services import PasswordResetService
from core.registration.services import RegistrationService
from core.registration.tasks import daily_maintenance_purge_task
from core.users.services import UserService
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

    def test_login_rejects_state_changed_after_authentication(self):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        for state in ("password", "inactive"):
            with self.subTest(state=state):
                user = self.create_user(email=f"login-{state}@example.com")

                def authenticated(**credentials):
                    result = authenticate(**credentials)
                    if state == "password":
                        changed = User.objects.get(pk=user.pk)
                        changed.set_password("ChangedPass!7395")
                        changed.save(update_fields=["password"])
                    else:
                        User.objects.filter(pk=user.pk).update(is_active=False)
                    return result

                with patch(
                    "core.auth.services.authenticate", side_effect=authenticated
                ):
                    with self.assertRaises(AuthenticationFailed):
                        AuthService.login_user(
                            user.email, self.password, "TestBrowser", "127.0.0.1"
                        )
                self.assertFalse(UserSession.objects.filter(user=user).exists())
                self.assertFalse(OutstandingToken.objects.filter(user=user).exists())

    def test_reauthentication_rejects_state_changed_before_mutation(self):
        for action in ("request", "confirm", "deactivate"):
            for state in ("password", "inactive"):
                with self.subTest(action=action, state=state):
                    user = self.create_user(email=f"{action}-{state}@example.com")
                    change = EmailChange(user=user, new_email="new@example.com")
                    change.set_code("123456")
                    change.save()

                    def reauthenticated(*args, **kwargs):
                        require_current_password(*args, **kwargs)
                        if state == "password":
                            changed = User.objects.get(pk=user.pk)
                            changed.set_password("ChangedPass!7395")
                            changed.save(update_fields=["password"])
                        else:
                            User.objects.filter(pk=user.pk).update(is_active=False)

                    module = (
                        "core.users.services"
                        if action == "deactivate"
                        else "core.email_change.services"
                    )
                    with patch(
                        f"{module}.require_current_password",
                        side_effect=reauthenticated,
                    ):
                        with self.assertRaises(AuthenticationFailed):
                            if action == "request":
                                EmailChangeService.request_change(
                                    user,
                                    f"other-{action}-{state}@example.com",
                                    self.password,
                                )
                            elif action == "confirm":
                                EmailChangeService.confirm_change(
                                    user, "123456", self.password
                                )
                            else:
                                UserService.deactivate_user(user, self.password)
                    change.refresh_from_db()
                    self.assertFalse(change.used)
                    self.assertEqual(change.new_email, "new@example.com")
                    current = User.objects.get(pk=user.pk)
                    self.assertEqual(current.email, user.email)
                    if state == "password":
                        self.assertTrue(current.is_active)
                        self.assertTrue(current.check_password("ChangedPass!7395"))

    def test_purge_preserves_registration_reissued_after_selection(self):
        for confirm in (False, True):
            with self.subTest(confirm=confirm):
                user = User.objects.create(
                    email=f"purge-{confirm}@example.com", is_active=False
                )
                User.objects.filter(pk=user.pk).update(
                    created_at=timezone.now() - timedelta(days=3)
                )
                EmailVerification.objects.create(
                    user=user,
                    code="expired",
                    expires_at=timezone.now() - timedelta(minutes=1),
                )
                selected, finished = Event(), Event()
                lock_users = User.objects.select_for_update

                def lock_after_reissue(*args, **kwargs):
                    if not selected.is_set():
                        selected.set()
                        if not finished.wait(timeout=10):
                            raise TimeoutError("Registration worker did not finish")
                    return lock_users(*args, **kwargs)

                def reissue():
                    try:
                        if not selected.wait(timeout=10):
                            raise TimeoutError("Purge did not select a candidate")
                        RegistrationService.request_registration(user.email)
                        if confirm:
                            RegistrationService.confirm_registration(
                                user.email,
                                self.email_code(),
                                "Registered Person",
                                self.password,
                            )
                    finally:
                        connections.close_all()
                        finished.set()

                with patch.object(
                    User.objects, "select_for_update", side_effect=lock_after_reissue
                ):
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(reissue)
                        result = daily_maintenance_purge_task()
                        future.result(timeout=20)
                self.assertEqual(result["registrations"], 0)
                user.refresh_from_db()
                self.assertEqual(user.is_active, confirm)
                self.assertGreater(
                    EmailVerification.objects.get(user=user).expires_at, timezone.now()
                )

    def test_reset_issuance_cannot_leave_old_email_code_after_change(self):
        user = self.create_user()
        EmailChangeService.request_change(user, "new@example.com", self.password)
        code = self.email_code()
        selected, finished = Event(), Event()
        lock_users = User.objects.select_for_update

        def lock_after_change(*args, **kwargs):
            if not selected.is_set():
                selected.set()
                if not finished.wait(timeout=10):
                    raise TimeoutError("Email-change worker did not finish")
            return lock_users(*args, **kwargs)

        def change_email():
            try:
                if not selected.wait(timeout=10):
                    raise TimeoutError("Reset did not reach user lock")
                EmailChangeService.confirm_change(user, code, self.password)
            finally:
                connections.close_all()
                finished.set()

        with patch.object(
            User.objects, "select_for_update", side_effect=lock_after_change
        ):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(change_email)
                PasswordResetService.request_reset(user.email)
                future.result(timeout=20)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(PasswordReset.objects.filter(user=user).exists())
