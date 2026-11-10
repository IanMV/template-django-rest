import hashlib

from django.core.cache import cache
from rest_framework import serializers
from rest_framework.exceptions import Throttled

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
    _limit(_key(f"{scope}:email", email.strip().lower()), 1, 60)


def limit_login_attempts(email, ip_address):
    _limit(_key("login:ip", ip_address or "unknown"), 30, 300)
    _limit(login_pair_key(email, ip_address), 10, 300)


def limit_code_verification_attempts(ip_address):
    _limit(_key("code-confirm:ip", ip_address or "unknown"), 15, 60)


def login_pair_key(email, ip_address):
    return _key("login:pair", f"{ip_address or 'unknown'}:{email.strip().lower()}")


def reset_login_attempts(email, ip_address):
    cache.delete(login_pair_key(email, ip_address))


def require_current_password(user, password):
    key = _key("reauth:user", user.pk)
    try:
        attempts = cache.get(key, 0)
    except Exception:
        raise ServiceUnavailable() from None
    if attempts >= 5:
        record_event("REAUTH", "BLOCKED")
        raise Throttled(wait=300)
    if user.check_password(password):
        cache.delete(key)
        return
    _limit(key, 5, 300)
    record_event("REAUTH", "FAILURE")
    raise serializers.ValidationError({"password": MSG_INVALID_PASSWORD})
