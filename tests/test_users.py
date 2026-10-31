from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from core.models.user import User, UserSession
from tests.base import ApiCase


class UserTests(ApiCase):
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
        response = self.client.post("/api/me/deactivate/")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(UserSession.objects.filter(user=user, is_active=True).exists())
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        self.assertEqual(response.cookies["access_token"]["max-age"], 0)
        self.assertEqual(response.cookies["refresh_token"]["max-age"], 0)
        self.assertEqual(other.get("/api/users/me/").status_code, 401)
