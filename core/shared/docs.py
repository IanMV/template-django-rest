from drf_spectacular.utils import OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
)
from rest_framework.serializers import CharField

from core.shared.response_messages import (
    MSG_CANNOT_DEACTIVATE_CURRENT_SESSION,
    MSG_CODE_INVALID,
    MSG_CODE_SENT,
    MSG_CODE_VALID,
    MSG_EMAIL_CHANGED,
    MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN,
    MSG_INVALID_PASSWORD,
    MSG_LOGIN_SUCCESSFUL,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_PASSWORD_RESET,
    MSG_REFRESH_TOKENS_SUCCESSFUL,
    MSG_SERVICE_UNAVAILABLE,
    MSG_USER_CREATED,
    MSG_USER_DEACTIVATED,
    MSG_USER_REVOKED_ALL_SESSIONS,
    MSG_USER_SESSION_DEACTIVATED,
    MSG_USER_SESSION_NOT_FOUND,
)

ServiceUnavailableSerializer = inline_serializer(
    "ServiceUnavailableResponse",
    {
        "detail": CharField(default=MSG_SERVICE_UNAVAILABLE),
    },
)

RequestSentSerializer = inline_serializer(
    "RequestSentSerializer",
    {
        "detail": CharField(default=MSG_CODE_SENT),
    },
)

CodeIsValidSerializer = inline_serializer(
    "CodeIsValidSerializer",
    {
        "detail": CharField(default=MSG_CODE_VALID),
    },
)

UserCreatedSerializer = inline_serializer(
    "UserCreateSuccessful",
    {
        "detail": CharField(default=MSG_USER_CREATED),
    },
)

PasswordResetSerializer = inline_serializer(
    "PasswordResetConfirmSuccess",
    {
        "detail": CharField(default=MSG_PASSWORD_RESET),
    },
)

NotAuthenticatedSerializer = inline_serializer(
    "NotAuthenticatedSerializer",
    {
        "detail": CharField(default=NotAuthenticated().default_detail),
    },
)

ForbiddenSerializer = inline_serializer(
    "ForbiddenResponse", {"detail": CharField(default=PermissionDenied().default_detail)}
)

IncorrectAuthenticationsCredentialsSerializer = inline_serializer(
    "IncorrectAuthenticationsCredentialsSerializer",
    {
        "detail": CharField(default=AuthenticationFailed().default_detail),
    },
)


CsrfForbiddenSerializer = inline_serializer(
    "CsrfForbiddenResponse",
    {
        "detail": CharField(),
    },
)

NewEmailChangedSerializer = inline_serializer(
    "NewEmailChangedSerializer",
    fields={
        "detail": CharField(
            default=MSG_EMAIL_CHANGED,
        )
    },
)

UserDeactivatedSerializer = inline_serializer(
    "UserDeactivatedSerializer",
    {
        "detail": CharField(default=MSG_USER_DEACTIVATED),
    },
)

UserRevokedAllSessionsSerializer = inline_serializer(
    "UserRevokedAllSessionsSerializer",
    {
        "detail": CharField(default=MSG_USER_REVOKED_ALL_SESSIONS),
    },
)

LoginSuccessfulSerializer = inline_serializer(
    "LoginSuccessfulResponse",
    {
        "detail": CharField(
            default=MSG_LOGIN_SUCCESSFUL,
            help_text="Access and refresh tokens are set in HttpOnly cookies; remember_me changes refresh lifetime, not the response body.",
        )
    },
)

LogoutSuccessfulSerializer = inline_serializer(
    "LogoutSuccessfulResponse",
    {"detail": CharField(default=MSG_LOGOUT_SUCCESSFUL)},
)

UserSessionDeactivatedSerializer = inline_serializer(
    "UserSessionDeactivatedSerializer",
    {"detail": CharField(default=MSG_USER_SESSION_DEACTIVATED)},
)

UserSessionNotFoundSerializer = inline_serializer(
    "UserSessionNotFoundSerializer",
    {"detail": CharField(default=MSG_USER_SESSION_NOT_FOUND)},
)

CannotDeactivateCurrentSessionSerializer = inline_serializer(
    "CannotDeactivateCurrentSessionSerializer",
    {
        "detail": CharField(default=MSG_CANNOT_DEACTIVATE_CURRENT_SESSION),
    },
)

RefreshTokensSuccessfulSerializer = inline_serializer(
    "RefreshTokensSuccessfulSerializer",
    {
        "detail": CharField(default=MSG_REFRESH_TOKENS_SUCCESSFUL),
    },
)

InvalidOrExpiredRefreshTokenSerializer = inline_serializer(
    "InvalidOrExpiredRefreshTokenSerializer",
    {
        "detail": CharField(default=MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN),
        "code": CharField(required=False),
    },
)

ThrottledSerializer = inline_serializer("ThrottledResponse", {"detail": CharField()})

ValidationErrorResponse = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
            ]
        },
    },
    description="Validation errors keyed by input field, or by detail.",
)

InvalidCodeExample = OpenApiExample(
    "Invalid or expired code",
    value={"code": str(MSG_CODE_INVALID)},
    response_only=True,
    status_codes=["400"],
)

CsrfFailureExample = OpenApiExample(
    "Missing CSRF header",
    value={"detail": "CSRF Failed: CSRF token missing."},
    response_only=True,
    status_codes=["403"],
)

RateLimitedExample = OpenApiExample(
    "Too many requests",
    value={"detail": "Request was throttled. Expected available in 60 seconds."},
    response_only=True,
    status_codes=["429"],
)

InvalidPasswordExample = OpenApiExample(
    "Invalid current password",
    value={"password": str(MSG_INVALID_PASSWORD)},
    response_only=True,
    status_codes=["400"],
)

ReauthRateLimitedExample = OpenApiExample(
    "Reauthentication throttled",
    value={"detail": "Request was throttled. Expected available in 300 seconds."},
    response_only=True,
    status_codes=["429"],
)
