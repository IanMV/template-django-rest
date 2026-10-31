import hashlib
import logging

from django.core.cache import cache
from rest_framework.exceptions import Throttled

from core.shared.exceptions import ServiceUnavailable

logger = logging.getLogger(__name__)


def limit_code_requests(scope: str, email: str, ip_address: str | None) -> None:
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

    if ip_address:
        ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
        try:
            if not cache.add(f"code-request:{scope}:ip:{ip_digest}", True, timeout=2):
                raise Throttled(wait=2)
        except Throttled:
            raise
        except Exception:
            logger.exception("Code issuance IP throttle unavailable; continuing")


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
