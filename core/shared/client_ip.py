from ipaddress import ip_address

from django.conf import settings


def get_client_ip(request) -> str | None:
    remote = request.META.get("REMOTE_ADDR")
    try:
        remote = str(ip_address(remote))
    except (ValueError, TypeError):
        remote = None

    count = settings.NUM_PROXIES
    if count > 0 and remote:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            chain = forwarded.split(",")
            if len(chain) >= count:
                try:
                    return str(ip_address(chain[-count].strip()))
                except ValueError:
                    pass
    return remote
