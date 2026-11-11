from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import hashers
from django.db import connection, connections
from django.test import override_settings

from core.models import PasswordReset, User
from core.password_reset.services import PasswordResetService
from tests.base import ApiTransactionCase


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ]
)
class PasswordUpgradeTests(ApiTransactionCase):
    replacement = "ReplacementPass!7395"

    def legacy_user(self, **fields):
        hasher = hashers.PBKDF2PasswordHasher()
        hasher.iterations = 1
        return User.objects.create(
            email="legacy@example.com",
            name="Legacy user",
            password=hasher.encode(self.password, "syntheticsalt"),
            **fields,
        )

    def reset_code(self, user):
        reset = PasswordReset(user=user)
        reset.set_code("123456")
        reset.save()

    def reset_after_verification(self, user, reset):
        original = hashers.verify_password
        encoded = user.password

        def verify(password, stored, **kwargs):
            result = original(password, stored, **kwargs)
            if stored == encoded and result == (True, True):
                reset()
            return result

        return patch("django.contrib.auth.hashers.verify_password", side_effect=verify)

    def assert_reset_preserved(self, user):
        user.refresh_from_db()
        self.assertTrue(user.check_password(self.replacement))
        self.assertFalse(user.check_password(self.password))
        self.assertEqual(user.session_version, 1)
        self.assertTrue(PasswordReset.objects.get(user=user).used)

    def test_sync_and_async_upgrade_preserve_password_change_contract(self):
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                user = self.legacy_user()
                updated_at = user.updated_at
                check = (
                    async_to_sync(user.acheck_password)
                    if asynchronous
                    else user.check_password
                )
                with patch(
                    "django.contrib.auth.password_validation.password_changed"
                ) as changed:
                    self.assertTrue(check(self.password))
                changed.assert_not_called()
                self.assertIsNone(user._password)
                self.assertEqual(
                    hashers.identify_hasher(user.password).algorithm, "md5"
                )
                saved = User.objects.get(pk=user.pk)
                self.assertEqual(saved.password, user.password)
                self.assertEqual(saved.updated_at, updated_at)
                user.delete()

    def test_wrong_and_unusable_passwords_do_not_write(self):
        user = self.legacy_user()
        for unusable in (False, True):
            if unusable:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            for asynchronous in (False, True):
                with self.subTest(unusable=unusable, asynchronous=asynchronous):
                    check = (
                        async_to_sync(user.acheck_password)
                        if asynchronous
                        else user.check_password
                    )
                    with self.assertNumQueries(0):
                        self.assertFalse(check("wrong"))

    def test_sync_and_async_conflicts_reject_password_without_overwriting_reset(self):
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                user = self.legacy_user()
                self.reset_code(user)
                check = (
                    async_to_sync(user.acheck_password)
                    if asynchronous
                    else user.check_password
                )
                with self.reset_after_verification(
                    user,
                    lambda: PasswordResetService.confirm_reset(
                        user.email, "123456", self.replacement
                    ),
                ):
                    self.assertFalse(check(self.password))
                self.assert_reset_preserved(user)
                user.delete()

    def test_api_and_admin_login_reject_conflicting_upgrades(self):
        for admin in (False, True):
            with self.subTest(admin=admin):
                user = self.legacy_user(is_staff=admin)
                self.reset_code(user)
                with self.reset_after_verification(
                    user,
                    lambda: PasswordResetService.confirm_reset(
                        user.email, "123456", self.replacement
                    ),
                ):
                    if admin:
                        response = self.client.post(
                            "/admin/login/",
                            {"username": user.email, "password": self.password},
                        )
                    else:
                        response = self.client.post(
                            "/api/login/",
                            {"email": user.email, "password": self.password},
                        )
                self.assertEqual(response.status_code, 200 if admin else 401)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assert_reset_preserved(user)
                self.login(user, password=self.replacement)
                self.client.post("/api/me/logout/")
                user.delete()

    def test_api_and_admin_login_upgrade_valid_credentials(self):
        for admin in (False, True):
            with self.subTest(admin=admin):
                user = self.legacy_user(is_staff=admin)
                self.bootstrap(self.client)
                response = self.client.post(
                    "/admin/login/" if admin else "/api/login/",
                    {
                        "username" if admin else "email": user.email,
                        "password": self.password,
                    },
                )
                self.assertEqual(response.status_code, 302 if admin else 200)
                self.assertEqual(self.client.get("/api/users/me/").status_code, 200)
                user.refresh_from_db()
                self.assertEqual(
                    hashers.identify_hasher(user.password).algorithm, "md5"
                )
                self.bootstrap(self.client)
                self.assertEqual(self.client.post("/api/me/logout/").status_code, 200)
                user.delete()

    def test_reset_before_verification_or_after_upgrade_keeps_new_password(self):
        for upgrade_first in (False, True):
            with self.subTest(upgrade_first=upgrade_first):
                user = self.legacy_user()
                self.reset_code(user)
                if upgrade_first:
                    self.assertTrue(user.check_password(self.password))
                PasswordResetService.confirm_reset(
                    user.email, "123456", self.replacement
                )
                user.refresh_from_db()
                self.assertFalse(user.check_password(self.password))
                self.assert_reset_preserved(user)
                user.delete()

    def test_upgrade_cannot_overwrite_reset_committed_on_another_connection(self):
        user = self.legacy_user()
        self.reset_code(user)
        main_connection = connection.connection

        def reset():
            try:
                self.assertTrue(connection.get_autocommit())
                PasswordResetService.confirm_reset(
                    user.email, "123456", self.replacement
                )
                self.assertIsNot(connection.connection, main_connection)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with self.reset_after_verification(
                user, lambda: executor.submit(reset).result(timeout=15)
            ):
                response = self.client.post(
                    "/api/login/", {"email": user.email, "password": self.password}
                )
        self.assertEqual(response.status_code, 401)
        self.assert_reset_preserved(user)
