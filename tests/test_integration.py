from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import IntegrityError, connection, connections
from rest_framework.exceptions import AuthenticationFailed

from core.auth.rate_limit import require_current_password
from core.auth.services import SessionService
from core.email_change.services import EmailChangeService
from core.models import EmailChange, User
from core.users.services import UserService
from tests.base import ApiCase, ApiTransactionCase


class StaleUserTests(ApiCase):
    def test_login_rechecks_authenticated_state(self):
        for state in ("password", "is_active", "email", "session_version", "deleted"):
            with self.subTest(state=state):
                user = self.create_user(email=f"{state}@example.com")

                def changed_after_authentication(**credentials):
                    result = authenticate(**credentials)
                    self.change_state(user, state)
                    return result

                with patch(
                    "core.auth.services.authenticate",
                    side_effect=changed_after_authentication,
                ):
                    response = self.client.post(
                        "/api/login/",
                        {"email": user.email, "password": self.password},
                        format="json",
                    )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def change_state(self, user, state):
        if state == "deleted":
            User.objects.filter(pk=user.pk).delete()
        else:
            value = {
                "password": "changed",
                "is_active": False,
                "email": f"changed-{user.pk}@example.com",
                "session_version": 1,
            }[state]
            User.objects.filter(pk=user.pk).update(**{state: value})

    def test_sensitive_operations_recheck_state_after_password_validation(self):
        for action in ("request", "confirm", "deactivate"):
            for state in (
                "password",
                "is_active",
                "email",
                "session_version",
                "deleted",
            ):
                with self.subTest(action=action, state=state):
                    cache.clear()
                    user = self.create_user(email=f"{action}-{state}@example.com")
                    change = EmailChange(user=user, new_email="new@example.com")
                    change.set_code("123456")
                    change.save()

                    def changed_after_reauthentication(*args):
                        require_current_password(*args)
                        self.change_state(user, state)

                    module = (
                        "core.users.services"
                        if action == "deactivate"
                        else "core.email_change.services"
                    )
                    with patch(
                        f"{module}.require_current_password",
                        side_effect=changed_after_reauthentication,
                    ):
                        with self.assertRaises(AuthenticationFailed):
                            if action == "request":
                                EmailChangeService.request_change(
                                    user, user.email, self.password
                                )
                            elif action == "confirm":
                                EmailChangeService.confirm_change(
                                    user, "123456", self.password
                                )
                            else:
                                UserService.deactivate_user(user, self.password)
                    if state != "deleted":
                        change.refresh_from_db()
                        self.assertFalse(change.used)
                    User.objects.filter(pk=user.pk).delete()


@skipUnless(
    connection.vendor == "postgresql", "Requires an isolated PostgreSQL test database"
)
class ProductionConcurrencyTests(ApiTransactionCase):
    def concurrent(self, operation):
        def worker():
            try:
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_case_variant_emails_create_one_account(self):
        ready = Barrier(2)

        def register():
            ready.wait(timeout=10)
            try:
                User.objects.create_user(
                    "Concurrent@EXAMPLE.COM", self.password, name="Concurrent"
                )
            except IntegrityError:
                return "duplicate"
            return "created"

        self.assertEqual(sorted(self.concurrent(register)), ["created", "duplicate"])
        self.assertEqual(User.objects.filter(email="concurrent@example.com").count(), 1)

    def test_concurrent_revocations_do_not_lose_increments(self):
        user = self.create_user()
        ready = Barrier(2)

        def revoke():
            ready.wait(timeout=10)
            SessionService.revoke_all_sessions(user)

        self.concurrent(revoke)
        user.refresh_from_db()
        self.assertEqual(user.session_version, 2)

    def test_concurrent_confirmation_consumes_code_once(self):
        from rest_framework.exceptions import ValidationError

        from core.models import EmailVerification
        from core.registration.services import RegistrationService

        user = User.objects.create(email="new@example.com", is_active=False)
        verification = EmailVerification(user=user)
        verification.set_code("123456")
        verification.save()
        ready = Barrier(2)

        def confirm():
            ready.wait(timeout=10)
            try:
                RegistrationService.confirm_registration(
                    user.email, "123456", "New Person", self.password
                )
            except ValidationError:
                return 400
            return 200

        self.assertEqual(sorted(self.concurrent(confirm)), [200, 400])
