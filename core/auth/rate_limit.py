import hashlib

from django.core.cache import cache
from rest_framework.exceptions import Throttled


def limit_code_requests(scope: str, email: str, ip_address: str | None) -> None:
    email_digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
    email_key = f"code-request:{scope}:email:{email_digest}"
    if not cache.add(email_key, True, timeout=60):
        raise Throttled(wait=60)

    if ip_address:
        ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
        if not cache.add(f"code-request:{scope}:ip:{ip_digest}", True, timeout=2):
            raise Throttled(wait=2)


def limit_login_attempts(email: str, ip_address: str | None) -> None:
    ip_address = ip_address or "unknown"
    ip_digest = hashlib.sha256(ip_address.encode()).hexdigest()
    keys = [
        (f"login:ip:{ip_digest}", 30),
        (login_pair_key(email, ip_address), 10),
    ]

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


def login_pair_key(email: str, ip_address: str) -> str:
    email_digest = hashlib.sha256(email.strip().casefold().encode()).hexdigest()
    pair_digest = hashlib.sha256(f"{ip_address}:{email_digest}".encode()).hexdigest()
    return f"login:pair:{pair_digest}"


def reset_login_attempts(email: str, ip_address: str | None) -> None:
    cache.delete(login_pair_key(email, ip_address or "unknown"))
