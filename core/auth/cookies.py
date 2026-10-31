from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse

REFRESH_COOKIE_PATH = "/api/refresh/"


def get_auth_cookie_kwargs(is_refresh=False):
    lifetime: timedelta = (
        settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        if is_refresh
        else settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    )

    return {
        "max_age": int(lifetime.total_seconds()),
        "httponly": settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
        "secure": settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
        "domain": settings.SIMPLE_JWT.get("AUTH_COOKIE_DOMAIN"),
        "path": (
            REFRESH_COOKIE_PATH
            if is_refresh
            else settings.SIMPLE_JWT.get("AUTH_COOKIE_PATH", "/")
        ),
        "samesite": settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
    }


def get_auth_cookie_name():
    return settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")


def clear_auth_cookies(response):
    cookie_kwargs = get_auth_cookie_kwargs()
    for name, path in (
        (get_auth_cookie_name(), cookie_kwargs["path"]),
        ("refresh_token", REFRESH_COOKIE_PATH),
    ):
        response.delete_cookie(
            name,
            path=path,
            domain=cookie_kwargs["domain"],
            samesite=cookie_kwargs["samesite"],
        )
    clear_legacy_refresh_cookie(response)


def clear_legacy_refresh_cookie(response):
    legacy = HttpResponse()
    legacy.delete_cookie(
        "refresh_token",
        path="/",
        domain=get_auth_cookie_kwargs()["domain"],
        samesite=get_auth_cookie_kwargs()["samesite"],
    )
    response["Set-Cookie"] = legacy.cookies["refresh_token"].OutputString()
