from django.contrib.auth import authenticate, login
from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import AuthenticationFailed

from core.auth.rate_limit import limit_login_attempts, reset_login_attempts
from core.models import User


def require_unchanged_user(previous, current):
    if (
        current is None
        or not current.is_active
        or current.password != previous.password
        or current.email != previous.email
        or current.session_version != previous.session_version
    ):
        raise AuthenticationFailed()


class SessionService:
    @staticmethod
    def revoke_all_sessions(user):
        User.objects.filter(pk=user.pk).update(session_version=F("session_version") + 1)


class AuthService:
    @staticmethod
    def login_user(request, email, password, ip_address):
        email = User.objects.normalize_email(email)
        limit_login_attempts(email, ip_address)
        user = authenticate(request=request, email=email, password=password)
        if user is None:
            raise AuthenticationFailed()

        with transaction.atomic():
            current = (
                User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
            )
            require_unchanged_user(user, current)
            login(request, current, backend=user.backend)
            request.session.save()

        reset_login_attempts(email, ip_address)
        return current
