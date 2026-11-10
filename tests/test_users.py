from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache

from core.models.user import User
from tests.base import ApiCase


class UserTests(ApiCase):
    def test_deactivation_requires_correct_password_without_side_effects(self):
        user = self.create_user()
        self.login(user)
        version = user.session_version
        missing = self.client.post("/api/me/deactivate/", {}, format="json")
        wrong = self.client.post(
            "/api/me/deactivate/", {"password": "wrong"}, format="json"
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("password", missing.data)
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(str(wrong.data["password"]), "Invalid current password.")
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.session_version, version)

    def test_deactivation_reauth_throttle_and_cache_failure(self):
        user = self.create_user()
        self.login(user)
        for _ in range(5):
            response = self.client.post(
                "/api/me/deactivate/", {"password": "wrong"}, format="json"
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/me/deactivate/", {"password": self.password}, format="json"
            ).status_code,
            429,
        )
        cache.clear()
        with patch("core.auth.rate_limit.cache.get", side_effect=RuntimeError("down")):
            with self.assertNoLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    "/api/me/deactivate/",
                    {"password": self.password},
                    format="json",
                )
        self.assertEqual(response.status_code, 503)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_deactivation_reauth_cache_reset_failure_fails_closed(self):
        user = self.create_user()
        self.login(user)
        with patch(
            "core.auth.rate_limit.cache.delete", side_effect=RuntimeError("down")
        ):
            with self.assertNoLogs("core.auth.rate_limit", level="ERROR"):
                response = self.client.post(
                    "/api/me/deactivate/",
                    {"password": self.password},
                    format="json",
                )
        self.assertEqual(response.status_code, 503)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

    def test_profile_returns_current_user(self):
        user = self.create_user()
        self.login(user)
        response = self.client.get("/api/users/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(user.pk))
        self.assertEqual(response.data["email"], user.email)
        self.assertNotIn("password", response.data)

    def test_regular_users_cannot_list_users(self):
        active = self.create_user()
        self.login(active)
        response = self.client.get("/api/users/list/")
        self.assertEqual(response.status_code, 403)

    def test_staff_list_is_paginated_and_excludes_inactive_users(self):
        staff = self.create_user(is_staff=True)
        inactive = self.create_user(email="inactive@example.com", is_active=False)
        self.create_user(email="second@example.com")
        self.login(staff)
        response = self.client.get("/api/users/list/?page_size=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertNotIn(
            inactive.email, [item["email"] for item in response.data["results"]]
        )

    def test_staff_page_size_has_explicit_maximum(self):
        staff = self.create_user(is_staff=True)
        User.objects.bulk_create(
            [
                User(email=f"person{n}@example.com", name="Person", password="!")
                for n in range(101)
            ]
        )
        self.login(staff)
        response = self.client.get("/api/users/list/?page_size=100000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 102)
        self.assertEqual(len(response.data["results"]), 100)

    def test_deactivate_revokes_all_sessions_and_clears_cookies(self):
        user = self.create_user()
        self.login(user)
        other = self.new_client()
        self.login(user, client=other, ip="127.0.0.2")
        response = self.client.post(
            "/api/me/deactivate/", {"password": self.password}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.session_version, 1)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"], 0)
        self.assertEqual(other.get("/api/users/me/").status_code, 401)

    def test_create_superuser_requires_password(self):
        with self.assertRaisesMessage(ValueError, "Superuser must have a password."):
            User.objects.create_superuser(
                email="admin_no_pass@example.com",
                password=None,
                name="Admin",
            )
        self.assertFalse(
            User.objects.filter(email="admin_no_pass@example.com").exists()
        )

        with self.assertRaisesMessage(ValueError, "Superuser must have a password."):
            User.objects.create_superuser(
                email="admin_empty_pass@example.com",
                password="",
                name="Admin",
            )
        self.assertFalse(
            User.objects.filter(email="admin_empty_pass@example.com").exists()
        )

    def test_custom_user_admin_creation_form(self):
        from core.admin import CustomUserCreationForm

        form = CustomUserCreationForm(
            {
                "email": "admin_staff_added@example.com",
                "name": "Staff Added",
                "password1": "StaffPass!7483",
                "password2": "StaffPass!7483",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.check_password("StaffPass!7483"))
        self.assertEqual(user.email, "admin_staff_added@example.com")

    def test_admin_user_deactivation_revokes_sessions(self):
        from django.contrib.admin.sites import AdminSite

        from core.admin import UserAdmin

        user = self.create_user()
        self.login(user)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 200)

        admin_instance = UserAdmin(User, AdminSite())
        user.is_active = False
        admin_instance.save_model(
            None, user, SimpleNamespace(changed_data=["is_active"]), change=True
        )

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.session_version, 1)
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)

    def test_admin_email_change_revokes_sessions(self):
        from django.contrib.admin.sites import AdminSite

        from core.admin import UserAdmin

        user = self.create_user()
        self.login(user)
        user.email = "changed@example.com"
        UserAdmin(User, AdminSite()).save_model(
            None, user, SimpleNamespace(changed_data=["email"]), change=True
        )
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)
