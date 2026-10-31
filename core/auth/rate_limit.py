import hashlib
import logging

from django.core.cache import cache
from rest_framework import serializers
from rest_framework.exceptions import Throttled

from core.audit.services import record_event
from core.shared.exceptions import ServiceUnavailable
from core.shared.response_messages import MSG_INVALID_PASSWORD

logger = logging.getLogger(__name__)


def limit_code_requests(scope: str, email: str, ip_address: str | None) -> None:
    if ip_address:
        ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
        try:
            if not cache.add(f"code-request:{scope}:ip:{ip_digest}", True, timeout=2):
                raise Throttled(wait=2)
        except Throttled:
            raise
        except Exception:
            logger.exception("Code issuance IP throttle unavailable; continuing")

    email_digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
    email_key = f"code-request:{scope}:email:{email_digest}"
    try:
        if not cache.add(email_key, True, timeout=60):
            raise Throttled(wait=60)
    except Throttled:
        raise
    except Exception as exc:
        logger.exception("Code issuance email throttle unavailable")
        raise ServiceUnavailable() from exc


def limit_login_attempts(email: str, ip_address: str | None) -> None:
    ip_address = ip_address or "unknown"
    ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
    keys = [
        (f"login:ip:{ip_digest}", 30),
        (login_pair_key(email, ip_address), 10),
    ]

    try:
        for key, maximum in keys:
            if cache.add(key, 1, timeout=300):
                continue
            try:
                attempts = cache.incr(key)
            except ValueError:
                cache.add(key, 1, timeout=300)
                continue
            if attempts > maximum:
                raise Throttled(wait=300)
    except Throttled:
        raise
    except Exception:
        logger.exception("Login throttle unavailable; continuing")


def limit_code_verification_attempts(ip_address: str | None) -> None:
    ip_digest = hashlib.sha256((ip_address or "unknown").encode()).hexdigest()
    key = f"code-verify:ip:{ip_digest}"
    try:
        if cache.add(key, 1, timeout=60):
            return
        try:
            attempts = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=60)
            return
        if attempts > 15:
            raise Throttled(wait=60)
    except Throttled:
        raise
    except Exception as exc:
        logger.exception("Code verification throttle unavailable")
        raise ServiceUnavailable() from exc


def login_pair_key(email: str, ip_address: str) -> str:
    email_digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
    pair_digest = hashlib.sha256(f"{ip_address}:{email_digest}".encode()).hexdigest()
    return f"login:pair:{pair_digest}"


def reset_login_attempts(email: str, ip_address: str | None) -> None:
    try:
        cache.delete(login_pair_key(email, ip_address or "unknown"))
    except Exception:
        logger.exception("Login throttle reset unavailable; continuing")


def require_current_password(user, password: str, *, request=None, action=None) -> None:
    user_digest = hashlib.sha256(str(user.pk).encode()).hexdigest()
    key = f"reauth:user:{user_digest}"
    try:
        attempts = cache.get(key, 0) or 0
    except Exception as exc:
        logger.exception("Reauthentication throttle unavailable")
        if request:
            record_event(request, user, "REAUTH", "FAILURE", {"action": action})
        raise ServiceUnavailable() from exc
    if attempts >= 5:
        if request:
            record_event(request, user, "REAUTH", "BLOCKED", {"action": action})
        raise Throttled(wait=300)

    valid = user.check_password(password)
    try:
        if valid:
            cache.delete(key)
        else:
            if cache.add(key, 1, timeout=300):
                failures = 1
            else:
                try:
                    failures = cache.incr(key)
                except ValueError:
                    cache.add(key, 1, timeout=300)
                    failures = 1
            if failures > 5:
                if request:
                    record_event(request, user, "REAUTH", "BLOCKED", {"action": action})
                raise Throttled(wait=300)
    except Throttled:
        raise
    except Exception as exc:
        logger.exception("Reauthentication throttle unavailable")
        if request:
            record_event(request, user, "REAUTH", "FAILURE", {"action": action})
        raise ServiceUnavailable() from exc
    if not valid:
        if request:
            record_event(request, user, "REAUTH", "FAILURE", {"action": action})
        raise serializers.ValidationError({"password": MSG_INVALID_PASSWORD})
