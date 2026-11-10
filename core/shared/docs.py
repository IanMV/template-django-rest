from drf_spectacular.utils import OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
)
from rest_framework.serializers import CharField

from core.shared.response_messages import (
    MSG_CODE_SENT,
    MSG_EMAIL_CHANGED,
    MSG_INVALID_PASSWORD,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_PASSWORD_RESET,
    MSG_SERVICE_UNAVAILABLE,
    MSG_USER_CREATED,
    MSG_USER_DEACTIVATED,
)

ServiceUnavailableSerializer = inline_serializer(
    "ServiceUnavailableResponse", {"detail": CharField(default=MSG_SERVICE_UNAVAILABLE)}
)
RequestSentSerializer = inline_serializer(
    "RequestSentResponse", {"detail": CharField(default=MSG_CODE_SENT)}
)
UserCreatedSerializer = inline_serializer(
    "UserCreatedResponse", {"detail": CharField(default=MSG_USER_CREATED)}
)
PasswordResetSerializer = inline_serializer(
    "PasswordResetResponse", {"detail": CharField(default=MSG_PASSWORD_RESET)}
)
NotAuthenticatedSerializer = inline_serializer(
    "NotAuthenticatedResponse",
    {"detail": CharField(default=NotAuthenticated().default_detail)},
)
ForbiddenSerializer = inline_serializer(
    "ForbiddenResponse",
    {"detail": CharField(default=PermissionDenied().default_detail)},
)
IncorrectAuthenticationsCredentialsSerializer = inline_serializer(
    "IncorrectCredentialsResponse",
    {"detail": CharField(default=AuthenticationFailed().default_detail)},
)
CsrfForbiddenSerializer = inline_serializer(
    "CsrfForbiddenResponse", {"detail": CharField()}
)
NewEmailChangedSerializer = inline_serializer(
    "EmailChangedResponse", {"detail": CharField(default=MSG_EMAIL_CHANGED)}
)
UserDeactivatedSerializer = inline_serializer(
    "UserDeactivatedResponse", {"detail": CharField(default=MSG_USER_DEACTIVATED)}
)
LogoutSuccessfulSerializer = inline_serializer(
    "LogoutResponse", {"detail": CharField(default=MSG_LOGOUT_SUCCESSFUL)}
)
ThrottledSerializer = inline_serializer("ThrottledResponse", {"detail": CharField()})
ValidationErrorResponse = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
            ],
        },
    },
    description="Validation errors keyed by input field, or by detail.",
)
CsrfFailureExample = OpenApiExample(
    "Missing CSRF header",
    value={"detail": "CSRF Failed: CSRF token missing."},
    response_only=True,
    status_codes=["403"],
)
InvalidPasswordExample = OpenApiExample(
    "Invalid current password",
    value={"password": str(MSG_INVALID_PASSWORD)},
    response_only=True,
    status_codes=["400"],
)
ReauthRateLimitedExample = OpenApiExample(
    "Reauthentication throttled",
    value={"detail": "Request was throttled."},
    response_only=True,
    status_codes=["429"],
)
