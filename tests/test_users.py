from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from core.models.user import UserSession
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

    def test_list_hides_inactive_users_from_regular_users(self):
        active = self.create_user()
        inactive = self.create_user(email="inactive@example.com", is_active=False)
        self.login(active)
        response = self.client.get("/api/users/list/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["email"] for item in response.data], [active.email])
        self.assertNotIn(inactive.email, [item["email"] for item in response.data])

    def test_staff_can_list_inactive_users(self):
        staff = self.create_user(is_staff=True)
        inactive = self.create_user(email="inactive@example.com", is_active=False)
        self.login(staff)
        response = self.client.get("/api/users/list/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(inactive.email, [item["email"] for item in response.data])

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
