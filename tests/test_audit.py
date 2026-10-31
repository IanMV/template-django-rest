import hashlib
from unittest.mock import patch

from django.contrib import admin
from django.db import DatabaseError

from core.audit.services import email_digest, record_event
from core.models import AuditLog
from tests.base import ApiCase


class AuditLogTests(ApiCase):
    def test_audit_log_snapshot_preserved_on_user_deletion(self):
        user = self.create_user(email="delete-audit@example.com")
        log = AuditLog.objects.create(
            user=user,
            user_uuid_snapshot=user.pk,
            event_type="LOGIN",
            status=AuditLog.Status.SUCCESS,
            details_json={},
        )
        user_pk = user.pk
        user.delete()
        log.refresh_from_db()
        self.assertIsNone(log.user)
        self.assertEqual(log.user_uuid_snapshot, user_pk)

    def test_details_json_strict_allowlist_filtering(self):
        user = self.create_user()
        fake_request = self.client.get("/api/login/").wsgi_request

        # LOGIN: only valid 64-char hex email_hash allowed, password/token stripped
        valid_hash = hashlib.sha256(b"test@example.com").hexdigest()
        log = record_event(
            fake_request,
            user,
            "LOGIN",
            "FAILURE",
            {
                "email_hash": valid_hash,
                "password": "SecretPassword123!",
                "raw_token": "jwt.secret.token",
                "otp": "123456",
            },
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.details_json, {"email_hash": valid_hash})
        self.assertNotIn("password", str(log.details_json))
        self.assertNotIn("raw_token", str(log.details_json))
        self.assertNotIn("otp", str(log.details_json))

        # REAUTH: only allowed actions accepted
        reauth_log = record_event(
            fake_request,
            user,
            "REAUTH",
            "FAILURE",
            {"action": "email_change_request", "password": "secret", "invalid_key": "val"},
        )
        self.assertEqual(reauth_log.details_json, {"action": "email_change_request"})

        # SESSION_REVOKE: only allowed scopes accepted
        revoke_log = record_event(
            fake_request,
            user,
            "SESSION_REVOKE",
            "SUCCESS",
            {"scope": "all", "extra": "data"},
        )
        self.assertEqual(revoke_log.details_json, {"scope": "all"})

        # LOGOUT has empty allowlist
        logout_log = record_event(
            fake_request,
            user,
            "LOGOUT",
            "SUCCESS",
            {"scope": "all", "password": "pass"},
        )
        self.assertEqual(logout_log.details_json, {})

    def test_unknown_user_login_stores_hash_only(self):
        unknown_email = "nonexistent@example.com"
        client = self.new_client()
        client.get("/api/login/")
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        response = client.post(
            "/api/login/",
            {"email": unknown_email, "password": "WrongPassword123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        expected_hash = email_digest(unknown_email)
        log = AuditLog.objects.filter(event_type="LOGIN", status="FAILURE").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details_json, {"email_hash": expected_hash})
        self.assertNotIn(unknown_email, str(log.details_json))
        self.assertIsNone(log.user)
        self.assertIsNone(log.user_uuid_snapshot)

    def test_audit_write_failure_does_not_break_login(self):
        user = self.create_user(email="resilient@example.com")
        with patch("core.audit.services.AuditLog.objects.create", side_effect=DatabaseError("DB Down")):
            client, response = self.login(user)
            self.assertEqual(response.status_code, 200)

    def test_blocked_events_deduplicated_by_cache(self):
        user = self.create_user()
        fake_request = self.client.get("/api/login/").wsgi_request
        details = {"action": "email_change_request"}
        first = record_event(fake_request, user, "REAUTH", "BLOCKED", details)
        self.assertIsNotNone(first)
        # Immediate duplicate should be suppressed by 60s cache
        second = record_event(fake_request, user, "REAUTH", "BLOCKED", details)
        self.assertIsNone(second)

    def test_audit_list_permissions_and_pagination(self):
        user = self.create_user(email="regular@example.com")
        staff = self.create_user(email="staff-audit@example.com", is_staff=True)

        for i in range(25):
            AuditLog.objects.create(
                user=user,
                user_uuid_snapshot=user.pk,
                event_type="LOGIN",
                status=AuditLog.Status.SUCCESS,
                details_json={},
            )

        # Unauthenticated: 401
        self.assertEqual(self.client.get("/api/audit/").status_code, 401)

        # Regular user: 403
        self.login(user)
        self.assertEqual(self.client.get("/api/audit/").status_code, 403)

        # Staff: 200 with 20 items per page by default
        self.login(staff)
        response = self.client.get("/api/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertGreaterEqual(response.data["count"], 25)
        self.assertIsNotNone(response.data["next"])

        # Page size query param with max_page_size=100
        page_response = self.client.get("/api/audit/?page_size=50")
        self.assertEqual(page_response.status_code, 200)
        self.assertEqual(len(page_response.data["results"]), response.data["count"])

    def test_audit_log_not_registered_in_django_admin(self):
        self.assertNotIn(AuditLog, admin.site._registry)

    def test_event_recording_in_core_flows(self):
        user = self.create_user(email="flow-audit@example.com")

        # 1. Login SUCCESS
        client, _ = self.login(user)
        self.assertTrue(
            AuditLog.objects.filter(
                user=user, event_type="LOGIN", status=AuditLog.Status.SUCCESS
            ).exists()
        )

        # 2. Staff user list access
        staff = self.create_user(email="staff-flow@example.com", is_staff=True)
        staff_client = self.new_client()
        self.login(staff, client=staff_client)
        staff_client.get("/api/users/list/")
        self.assertTrue(
            AuditLog.objects.filter(
                user=staff, event_type="USER_LIST_ACCESS", status=AuditLog.Status.SUCCESS
            ).exists()
        )

        # 3. Refresh SUCCESS
        with self.captureOnCommitCallbacks(execute=True):
            refresh_resp = client.post("/api/refresh/")
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                user=user, event_type="REFRESH", status=AuditLog.Status.SUCCESS
            ).exists()
        )

        # 4. Refresh REUSE BLOCKED
        old_refresh = client.cookies["refresh_token"].value
        # Rotate once more
        with self.captureOnCommitCallbacks(execute=True):
            client.post("/api/refresh/")
        # Replay old refresh
        client.cookies["refresh_token"] = old_refresh
        with self.captureOnCommitCallbacks(execute=True):
            reuse_resp = client.post("/api/refresh/")
        self.assertEqual(reuse_resp.status_code, 401)
        self.assertTrue(
            AuditLog.objects.filter(
                user=user, event_type="REFRESH_REUSE", status=AuditLog.Status.BLOCKED
            ).exists()
        )

        # 5. Session revoke (other)
        client_a = self.new_client()
        self.login(user, client=client_a, ip="10.0.0.1")
        client_b = self.new_client()
        self.login(user, client=client_b, ip="10.0.0.2")
        sessions_resp = client_b.get("/api/sessions/")
        other_session = [s for s in sessions_resp.data if not s["current"]][0]
        with self.captureOnCommitCallbacks(execute=True):
            del_resp = client_b.delete(f"/api/sessions/{other_session['id']}/")
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                user=user,
                event_type="SESSION_REVOKE",
                status=AuditLog.Status.SUCCESS,
                details_json={"scope": "other"},
            ).exists()
        )

        # 6. Logout SUCCESS
        with self.captureOnCommitCallbacks(execute=True):
            logout_resp = client_b.post("/api/me/logout/")
        self.assertEqual(logout_resp.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                user=user, event_type="LOGOUT", status=AuditLog.Status.SUCCESS
            ).exists()
        )

        # 7. Reauth FAILURE (wrong password during email change request)
        active_user = self.create_user(email="reauth-audit@example.com")
        reauth_client, _ = self.login(active_user)
        fail_reauth = reauth_client.post(
            "/api/email-change/request/",
            {"new_email": "new-reauth@example.com", "password": "WrongPassword!"},
            format="json",
        )
        self.assertEqual(fail_reauth.status_code, 400)
        self.assertTrue(
            AuditLog.objects.filter(
                user=active_user,
                event_type="REAUTH",
                status=AuditLog.Status.FAILURE,
                details_json={"action": "email_change_request"},
            ).exists()
        )
