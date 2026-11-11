from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import EmailChange, EmailVerification, PasswordReset, User


class Command(BaseCommand):
    help = "Remove abandoned registrations, expired codes and expired Django sessions."

    def handle(self, *args, **options):
        now = timezone.now()
        abandoned = User.objects.filter(
            Q(emailverification__isnull=True)
            | Q(emailverification__expires_at__lte=now)
            | Q(emailverification__used=True),
            is_active=False,
            password="",
            is_staff=False,
            is_superuser=False,
            name="",
            last_login__isnull=True,
            session_version=0,
            groups__isnull=True,
            user_permissions__isnull=True,
            logentry__isnull=True,
            passwordreset__isnull=True,
            emailchange__isnull=True,
            created_at__lt=now - timedelta(hours=48),
        )
        total = 0
        while ids := list(abandoned.order_by("pk").values_list("pk", flat=True)[:500]):
            with transaction.atomic():
                list(
                    # Also serialize foreign-key additions with account deletion.
                    User.objects.select_for_update().filter(pk__in=ids).order_by("pk")
                )
                _, counts = abandoned.filter(pk__in=ids).delete()
                total += counts.get(User._meta.label, 0)

        for model in (EmailVerification, PasswordReset, EmailChange):
            expired = model.objects.filter(expires_at__lte=now)
            if model is EmailVerification:
                # Keep abandoned-registration markers until the user is eligible for cleanup.
                expired = expired.exclude(user__is_active=False, user__password="")
            while ids := list(
                expired.order_by("pk").values_list("pk", flat=True)[:500]
            ):
                expired.filter(pk__in=ids).delete()
        call_command("clearsessions", verbosity=options["verbosity"])
        self.stdout.write(f"Abandoned registrations removed: {total}")
