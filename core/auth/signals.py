from datetime import timedelta

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_in)
def set_fixed_session_expiry(sender, request, **kwargs):
    # Apply the same absolute deadline to API and Django admin logins.
    request.session.set_expiry(
        timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE)
    )
