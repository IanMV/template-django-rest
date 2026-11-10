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
            | Q(emailverification__used=False, emailverification__expires_at__lte=now),
            is_active=False,
            password="",
            is_staff=False,
            is_superuser=False,
            created_at__lt=now - timedelta(hours=48),
        )
        total = 0
        while ids := list(abandoned.order_by("pk").values_list("pk", flat=True)[:500]):
            with transaction.atomic():
                list(
                    User.objects.select_for_update(no_key=True)
                    .filter(pk__in=ids)
                    .order_by("pk")
                )
                _, counts = abandoned.filter(pk__in=ids).delete()
                total += counts.get(User._meta.label, 0)

        for model in (EmailVerification, PasswordReset, EmailChange):
            expired = model.objects.filter(expires_at__lte=now)
            if model is EmailVerification:
                # Keep abandoned-registration markers until the user is eligible for cleanup.
                expired = expired.exclude(
                    user__is_active=False, user__password="", used=False
                )
            while ids := list(
                expired.order_by("pk").values_list("pk", flat=True)[:500]
            ):
                expired.filter(pk__in=ids).delete()
        call_command("clearsessions", verbosity=options["verbosity"])
        self.stdout.write(f"Abandoned registrations removed: {total}")
