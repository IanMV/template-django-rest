import hashlib

from django.core.cache import cache
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import Throttled

from core.models import User
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import MSG_INVALID_PASSWORD
from core.shared.security import record_event


def _key(scope, identity):
    return f"auth:{scope}:{hashlib.sha256(str(identity).encode()).hexdigest()}"


def _limit(key, maximum, timeout):
    # shortcut: local counters reset on restart and are per process; use shared storage before requiring global limits.
    try:
        if cache.add(key, 1, timeout=timeout):
            return
        try:
            attempts = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=timeout)
            return
    except Exception:
        raise ServiceUnavailable() from None
    if attempts > maximum:
        raise Throttled(wait=timeout)


def limit_code_requests(scope, email, ip_address):
    _limit(_key(f"{scope}:ip", ip_address or "unknown"), 1, 2)
    _limit(_key(f"{scope}:email", User.objects.normalize_email(email)), 1, 60)


def limit_login_attempts(email, ip_address):
    for key, maximum in (
        (login_pair_key(email, ip_address), 10),
        (_key("login:ip", ip_address or "unknown"), 30),
    ):
        try:
            attempts = cache.get(key, 0)
        except Exception:
            raise ServiceUnavailable() from None
        if attempts >= maximum:
            raise Throttled(wait=300)
    _limit(login_pair_key(email, ip_address), 10, 300)


def record_login_failure(ip_address):
    _limit(_key("login:ip", ip_address or "unknown"), 30, 300)


def limit_code_verification_attempts(ip_address):
    _limit(_key("code-confirm:ip", ip_address or "unknown"), 15, 60)


def login_pair_key(email, ip_address):
    return _key(
        "login:pair", f"{ip_address or 'unknown'}:{User.objects.normalize_email(email)}"
    )


def reset_login_attempts(email, ip_address):
    try:
        cache.delete(login_pair_key(email, ip_address))
    except Exception:
        raise ServiceUnavailable() from None


def require_current_password(user, password):
    from core.auth.services import require_unchanged_user

    with transaction.atomic():
        current = User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
        require_unchanged_user(user, current)
        key = _key("reauth:user", user.pk)
        try:
            attempts = cache.get(key, 0)
        except Exception:
            raise ServiceUnavailable() from None
        if attempts >= 5:
            record_event("REAUTH", "BLOCKED")
            raise Throttled(wait=300)
        if user.check_password(password):
            try:
                cache.delete(key)
            except Exception:
                raise ServiceUnavailable() from None
            return
        _limit(key, 5, 300)
        record_event("REAUTH", "FAILURE")
        raise serializers.ValidationError({"password": MSG_INVALID_PASSWORD})
