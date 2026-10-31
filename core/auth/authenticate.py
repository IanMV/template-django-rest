from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.auth.session_cache import session_is_active


def dummy_get_response(request):
    return None


def enforce_csrf(request):
    check = CSRFCheck(dummy_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


class CustomAuthentication(JWTAuthentication):
    db_only_routes = frozenset(
        {
            "email-change-request",
            "email-change-verify",
            "email-change-confirm",
            "deactivate-self",
            "user-sessions-deactivate",
            "revoke-sessions",
            "logout",
        }
    )

    def authenticate(self, request):
        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token")
        raw_token = request.COOKIES.get(cookie_name)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        match = request.resolver_match
        if not session_is_active(
            validated_token,
            use_cache=not (match and match.url_name in self.db_only_routes),
        ):
            raise exceptions.AuthenticationFailed()
        if request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ):
            enforce_csrf(request)
        return self.get_user(validated_token), validated_token


class CustomAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.auth.authenticate.CustomAuthentication"
    name = ["accessCookie", "refreshCookie", "csrfHeader"]

    def get_security_requirement(self, auto_schema):
        requirement = {"accessCookie": []}
        if auto_schema.method not in ("GET", "HEAD", "OPTIONS"):
            requirement["csrfHeader"] = []
        return requirement

    def get_security_definition(self, auto_schema):
        header_name = settings.CSRF_HEADER_NAME.removeprefix("HTTP_").replace("_", "-")
        return [
            {
                "type": "apiKey",
                "in": "cookie",
                "name": settings.SIMPLE_JWT.get("AUTH_COOKIE", "access_token"),
                "description": "HttpOnly access JWT set by POST /api/login/; the browser sends it automatically.",
            },
            {
                "type": "apiKey",
                "in": "cookie",
                "name": "refresh_token",
                "description": "HttpOnly refresh JWT set by POST /api/login/; used by POST /api/refresh/.",
            },
            {
                "type": "apiKey",
                "in": "header",
                "name": header_name,
                "description": "Copy the readable csrftoken cookie, or use same-origin Swagger UI injection.",
            },
        ]
