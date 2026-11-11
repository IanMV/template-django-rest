from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication


class CustomAuthentication(SessionAuthentication):
    def authenticate(self, request):
        # Public mutations need CSRF too, especially login and code issuance.
        self.enforce_csrf(request)
        authenticated = super().authenticate(request)
        if authenticated is not None and not authenticated[0].has_usable_password():
            return None
        return authenticated

    def authenticate_header(self, request):
        return "Session"


class CustomAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.auth.authenticate.CustomAuthentication"
    name = ["sessionCookie", "csrfHeader"]

    def get_security_requirement(self, auto_schema):
        requirement = {"sessionCookie": []}
        if auto_schema.method not in ("GET", "HEAD", "OPTIONS"):
            requirement["csrfHeader"] = []
        return requirement

    def get_security_definition(self, auto_schema):
        from django.conf import settings

        return [
            {"type": "apiKey", "in": "cookie", "name": settings.SESSION_COOKIE_NAME},
            {"type": "apiKey", "in": "header", "name": "X-CSRFTOKEN"},
        ]
