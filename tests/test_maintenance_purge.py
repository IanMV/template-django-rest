from datetime import timedelta

from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AuditLog, EmailVerification, User, UserSession
from core.registration.tasks import daily_maintenance_purge_task
from tests.base import ApiCase


class MaintenancePurgeTests(ApiCase):
    def test_celery_beat_schedule_configured_for_three_am(self):
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn("daily-maintenance-purge", schedule)
        entry = schedule["daily-maintenance-purge"]
        self.assertEqual(
            entry["task"], "core.registration.tasks.daily_maintenance_purge_task"
        )
        # crontab(hour=3, minute=0)
        self.assertEqual(entry["schedule"].hour, {3})
        self.assertEqual(entry["schedule"].minute, {0})

    def test_purge_unconfirmed_abandoned_registrations_preserves_self_deactivated_users(self):
        now = timezone.now()

        # 1. Abandoned unconfirmed user: inactive, password="", created > 48h ago, verification unused and expired
        abandoned_user = User.objects.create(
            email="abandoned@example.com",
            name="Abandoned",
            password="",
            is_active=False,
        )
        User.objects.filter(pk=abandoned_user.pk).update(created_at=now - timedelta(hours=50))
        EmailVerification.objects.create(
            user=abandoned_user,
            code="hashcode",
            expires_at=now - timedelta(minutes=1),
            used=False,
        )

        # 2. Recent unconfirmed user (< 48h): should NOT be deleted
        recent_user = User.objects.create(
            email="recent@example.com",
            name="Recent",
            password="",
            is_active=False,
        )
        User.objects.filter(pk=recent_user.pk).update(created_at=now - timedelta(hours=24))
        EmailVerification.objects.create(
            user=recent_user,
            code="hashcode2",
            expires_at=now - timedelta(minutes=1),
            used=False,
        )

        # 3. Unconfirmed user with unexpired code: should NOT be deleted
        unexpired_user = User.objects.create(
            email="unexpired@example.com",
            name="Unexpired",
            password="",
            is_active=False,
        )
        User.objects.filter(pk=unexpired_user.pk).update(created_at=now - timedelta(hours=50))
        EmailVerification.objects.create(
            user=unexpired_user,
            code="hashcode3",
            expires_at=now + timedelta(minutes=10),
            used=False,
        )

        # 4. Confirmed, then SELF-DEACTIVATED user (> 48h old): MUST SURVIVE!
        deactivated_user = self.create_user(email="self-deactivated@example.com")
        deactivated_user.deactivate()
        User.objects.filter(pk=deactivated_user.pk).update(created_at=now - timedelta(days=5))
        # Even if an old verification exists
        EmailVerification.objects.create(
            user=deactivated_user,
            code="hashcode4",
            expires_at=now - timedelta(hours=1),
            used=True,
        )

        # 5. Active user: MUST SURVIVE!
        active_user = self.create_user(email="active-keep@example.com")

        # Run maintenance purge
        results = daily_maintenance_purge_task()

        self.assertEqual(results["registrations"], 1)
        self.assertFalse(User.objects.filter(pk=abandoned_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=recent_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=unexpired_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=deactivated_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=active_user.pk).exists())

    def test_purge_sessions_and_absolute_cap(self):
        now = timezone.now()
        user = self.create_user(email="session-purge@example.com")

        # 1. Inactive session older than 30 days -> should be deleted
        stale_inactive = UserSession.objects.create(
            user=user,
            device_name="Old Device",
            ip_address="127.0.0.1",
            access_jti="jti-stale-access",
            refresh_jti="jti-stale-refresh",
            is_active=False,
        )
        UserSession.objects.filter(pk=stale_inactive.pk).update(
            last_activity=now - timedelta(days=31)
        )

        # 2. Inactive session recent (< 30 days) -> should NOT be deleted
        recent_inactive = UserSession.objects.create(
            user=user,
            device_name="Recent Inactive",
            ip_address="127.0.0.1",
            access_jti="jti-recent-access",
            refresh_jti="jti-recent-refresh",
            is_active=False,
        )
        UserSession.objects.filter(pk=recent_inactive.pk).update(
            last_activity=now - timedelta(days=10)
        )

        # 3. Active session past standard absolute cap (30 days) -> should be deactivated and deleted
        cap_active = UserSession.objects.create(
            user=user,
            device_name="Cap Exceeded",
            ip_address="127.0.0.1",
            access_jti="jti-cap-access",
            refresh_jti="jti-cap-refresh",
            is_active=True,
            remember_me=False,
        )
        UserSession.objects.filter(pk=cap_active.pk).update(
            created_at=now - settings.SESSION_ABSOLUTE_LIFETIME - timedelta(hours=1)
        )

        # 4. Active remembered session within cap (e.g. 5 days old) -> should NOT be deleted
        remembered_active = UserSession.objects.create(
            user=user,
            device_name="Remembered Valid",
            ip_address="127.0.0.1",
            access_jti="jti-rem-access",
            refresh_jti="jti-rem-refresh",
            is_active=True,
            remember_me=True,
        )
        UserSession.objects.filter(pk=remembered_active.pk).update(
            created_at=now - timedelta(days=5)
        )

        results = daily_maintenance_purge_task()

        self.assertEqual(results["sessions"], 2)
        self.assertFalse(UserSession.objects.filter(pk=stale_inactive.pk).exists())
        self.assertTrue(UserSession.objects.filter(pk=recent_inactive.pk).exists())
        self.assertFalse(UserSession.objects.filter(pk=cap_active.pk).exists())
        self.assertTrue(UserSession.objects.filter(pk=remembered_active.pk).exists())

    def test_audit_log_purge_respects_retention_days(self):
        now = timezone.now()
        user = self.create_user(email="audit-purge@example.com")

        old_log = AuditLog.objects.create(
            user=user,
            user_uuid_snapshot=user.pk,
            event_type="LOGIN",
            status=AuditLog.Status.SUCCESS,
        )
        AuditLog.objects.filter(pk=old_log.pk).update(created_at=now - timedelta(days=100))

        recent_log = AuditLog.objects.create(
            user=user,
            user_uuid_snapshot=user.pk,
            event_type="LOGIN",
            status=AuditLog.Status.SUCCESS,
        )
        AuditLog.objects.filter(pk=recent_log.pk).update(created_at=now - timedelta(days=10))

        # Default AUDIT_RETENTION_DAYS is None -> nothing deleted
        with override_settings(AUDIT_RETENTION_DAYS=None):
            res_none = daily_maintenance_purge_task()
            self.assertEqual(res_none["audit_logs"], 0)
            self.assertTrue(AuditLog.objects.filter(pk=old_log.pk).exists())
            self.assertTrue(AuditLog.objects.filter(pk=recent_log.pk).exists())

        # With AUDIT_RETENTION_DAYS=60 -> old_log deleted, recent_log kept
        with override_settings(AUDIT_RETENTION_DAYS=60):
            res_retained = daily_maintenance_purge_task()
            self.assertEqual(res_retained["audit_logs"], 1)
            self.assertFalse(AuditLog.objects.filter(pk=old_log.pk).exists())
            self.assertTrue(AuditLog.objects.filter(pk=recent_log.pk).exists())

    def test_flushexpiredtokens_flushes_expired_simplejwt_tokens(self):
        now = timezone.now()
        user = self.create_user(email="jwt-flush@example.com")
        refresh = RefreshToken.for_user(user)

        outstanding = OutstandingToken.objects.get(jti=str(refresh["jti"]))
        # Set token to expired
        OutstandingToken.objects.filter(pk=outstanding.pk).update(expires_at=now - timedelta(days=1))
        BlacklistedToken.objects.create(token=outstanding)

        res = daily_maintenance_purge_task()
        self.assertGreaterEqual(res["tokens"], 1)
        self.assertFalse(OutstandingToken.objects.filter(pk=outstanding.pk).exists())
