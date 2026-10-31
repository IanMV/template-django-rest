from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from core.auth.services import SessionService
from core.models import AuditLog, User, UserSession

BATCH_SIZE = 500


def delete_batches(queryset, model):
    total = 0
    while ids := list(queryset.order_by("pk").values_list("pk", flat=True)[:BATCH_SIZE]):
        with transaction.atomic():
            _, counts = model.objects.filter(pk__in=ids).delete()
            total += counts.get(model._meta.label, 0)
    return total


@shared_task(ignore_result=True)
def daily_maintenance_purge_task():
    now = timezone.now()
    abandoned = User.objects.filter(
        is_active=False,
        created_at__lt=now - timedelta(hours=48),
        emailverification__isnull=False,
        emailverification__used=False,
        emailverification__expires_at__lte=now,
    )
    registrations = delete_batches(abandoned, User)

    expired_sessions = (
        Q(is_active=False, last_activity__lt=now - timedelta(days=30))
        | Q(
            is_active=True,
            remember_me=False,
            created_at__lte=now - settings.SESSION_ABSOLUTE_LIFETIME,
        )
        | Q(
            is_active=True,
            remember_me=True,
            created_at__lte=now - settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME,
        )
    )
    sessions = 0
    while ids := list(
        UserSession.objects.filter(expired_sessions)
        .order_by("pk")
        .values_list("pk", flat=True)[:BATCH_SIZE]
    ):
        with transaction.atomic():
            rows = list(
                UserSession.objects.select_for_update()
                .filter(pk__in=ids)
                .filter(expired_sessions)
            )
            for session in rows:
                if session.is_active:
                    SessionService.deactivate_session(session.user, session.pk)
            if rows:
                _, counts = UserSession.objects.filter(pk__in=[row.pk for row in rows]).delete()
                sessions += counts.get(UserSession._meta.label, 0)

    retention = settings.AUDIT_RETENTION_DAYS
    audits = (
        delete_batches(AuditLog.objects.filter(created_at__lt=now - timedelta(days=retention)), AuditLog)
        if retention is not None
        else 0
    )
    tokens = OutstandingToken.objects.filter(expires_at__lte=now).count()
    call_command("flushexpiredtokens", verbosity=0)
    return {
        "registrations": registrations,
        "sessions": sessions,
        "audit_logs": audits,
        "tokens": tokens,
    }
