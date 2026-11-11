from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.db import (
    IntegrityError,
    OperationalError,
    connection,
    connections,
    transaction,
)
from django.db.models.query import QuerySet
from django.utils import timezone
from rest_framework.exceptions import Throttled, ValidationError

from core.auth.rate_limit import _key, require_current_password
from core.email_change.services import EmailChangeService
from core.models import EmailChange, EmailVerification, PasswordReset, User
from core.password_reset.services import PasswordResetService
from core.registration.services import RegistrationService
from tests.base import ApiTransactionCase


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class AuditConcurrencyTests(ApiTransactionCase):
    def worker(self, operation):
        try:
            return operation()
        finally:
            connections.close_all()

    def test_reauthentication_serializes_guard_hash_and_counter(self):
        user = self.create_user()
        cache.set(_key("reauth:user", user.pk), 4, 300)
        entered, release = Event(), Event()

        def check(_user, password):
            if password == "wrong":
                entered.set()
                if not release.wait(timeout=10):
                    raise RuntimeError("Test coordination timed out")
                return False
            return True

        def authenticate(password):
            try:
                require_current_password(user, password)
            except ValidationError:
                return 400
            except Throttled:
                return 429
            return 200

        with patch.object(
            User, "check_password", autospec=True, side_effect=check
        ) as checks:
            with ThreadPoolExecutor(max_workers=2) as executor:
                wrong = executor.submit(self.worker, lambda: authenticate("wrong"))
                try:
                    self.assertTrue(entered.wait(timeout=10))
                    correct = executor.submit(
                        self.worker, lambda: authenticate(self.password)
                    )
                    with self.assertRaises(TimeoutError):
                        correct.result(timeout=0.2)
                finally:
                    release.set()
                self.assertEqual(wrong.result(timeout=10), 400)
                self.assertEqual(correct.result(timeout=10), 429)
        self.assertEqual(checks.call_count, 1)

    def test_registration_get_or_create_already_holds_the_cleanup_lock(self):
        user = User.objects.create(email="pending@example.com", is_active=False)
        original = QuerySet.get_or_create

        def try_lock():
            try:
                with transaction.atomic():
                    User.objects.select_for_update(nowait=True).get(pk=user.pk)
                return True
            except OperationalError as exc:
                if getattr(exc.__cause__, "sqlstate", None) != "55P03":
                    raise
                return False

        def inspect_lock(queryset, *args, **kwargs):
            result = original(queryset, *args, **kwargs)
            if queryset.model is User:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    self.assertFalse(
                        executor.submit(self.worker, try_lock).result(timeout=10)
                    )
            return result

        with patch.object(QuerySet, "get_or_create", inspect_lock):
            RegistrationService.request_registration(user.email)
        self.assertTrue(EmailVerification.objects.filter(user=user).exists())

    def test_independent_worker_cooldowns_cannot_replace_recent_codes(self):
        user = self.create_user()
        for flow, model, operation in (
            (
                "registration",
                EmailVerification,
                lambda: RegistrationService.request_registration("pending@example.com"),
            ),
            (
                "password-reset",
                PasswordReset,
                lambda: PasswordResetService.request_reset(user.email),
            ),
            (
                "email-change",
                EmailChange,
                lambda: EmailChangeService.request_change(
                    user, "new@example.com", self.password
                ),
            ),
        ):
            with self.subTest(flow=flow):
                cache.clear()
                ready = Barrier(2)

                def issue():
                    ready.wait(timeout=10)
                    operation()

                module = {
                    "registration": "core.registration.services",
                    "password-reset": "core.password_reset.services",
                    "email-change": "core.email_change.services",
                }[flow]
                with (
                    patch(f"{module}.limit_code_requests"),
                    patch(f"{module}.send_email_token") as send,
                ):
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = [
                            executor.submit(self.worker, issue) for _ in range(2)
                        ]
                        for future in futures:
                            future.result(timeout=15)
                self.assertEqual(model.objects.count(), 1)
                self.assertEqual(send.call_count, 1)

    def test_history_post_outside_atomic_does_not_request_a_row_lock(self):
        owner = self.create_user()
        self.login(
            self.create_user(
                email="admin@example.com", is_staff=True, is_superuser=True
            )
        )
        self.assertFalse(connection.in_atomic_block)
        response = self.client.post(f"/admin/core/user/{owner.pk}/history/")
        self.assertEqual(response.status_code, 200)

    def test_cleanup_preserves_enrichment_committed_before_lock(self):
        user = User.objects.create(email="pending@example.com", is_active=False)
        User.objects.filter(pk=user.pk).update(
            created_at=timezone.now() - timedelta(hours=49)
        )
        group = Group.objects.create(name="Committed enrichment")
        lock = User.objects.select_for_update

        def enrich_before_lock(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(self.worker, lambda: user.groups.add(group)).result(
                    timeout=10
                )
            return lock(*args, **kwargs)

        with patch.object(
            User.objects, "select_for_update", side_effect=enrich_before_lock
        ):
            call_command("cleanup_auth", stdout=StringIO())
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertTrue(user.groups.filter(pk=group.pk).exists())

    def test_cleanup_blocks_foreign_key_addition_until_deletion_commits(self):
        user = User.objects.create(email="pending@example.com", is_active=False)
        User.objects.filter(pk=user.pk).update(
            created_at=timezone.now() - timedelta(hours=49)
        )
        group = Group.objects.create(name="Concurrent enrichment")
        attempting = Event()
        delete = QuerySet.delete
        additions = []

        def add_group():
            try:
                with transaction.atomic():
                    attempting.set()
                    user.groups.add(group)
                return True
            except IntegrityError:
                return False

        with ThreadPoolExecutor(max_workers=1) as executor:

            def inspect_delete(queryset):
                if queryset.model is User:
                    addition = executor.submit(self.worker, add_group)
                    additions.append(addition)
                    self.assertTrue(attempting.wait(timeout=10))
                    with self.assertRaises(TimeoutError):
                        addition.result(timeout=0.2)
                return delete(queryset)

            with patch.object(QuerySet, "delete", inspect_delete):
                call_command("cleanup_auth", stdout=StringIO())
            self.assertEqual(len(additions), 1)
            self.assertFalse(additions[0].result(timeout=10))
        self.assertFalse(User.objects.filter(pk=user.pk).exists())


class AdminAutocommitTests(ApiTransactionCase):
    def test_history_does_not_attempt_a_lock_outside_atomic(self):
        owner = self.create_user()
        self.login(
            self.create_user(
                email="admin@example.com", is_staff=True, is_superuser=True
            )
        )
        self.assertFalse(connection.in_atomic_block)
        with patch.object(
            QuerySet,
            "select_for_update",
            side_effect=AssertionError("Unexpected row lock"),
        ):
            response = self.client.post(f"/admin/core/user/{owner.pk}/history/")
        self.assertEqual(response.status_code, 200)
