from django.contrib.auth import logout
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.rate_limit import limit_code_verification_attempts
from core.password_reset.serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from core.password_reset.services import PasswordResetService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CsrfForbiddenSerializer,
    PasswordResetSerializer,
    RequestSentSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import MSG_CODE_SENT, MSG_PASSWORD_RESET
from core.shared.security import record_event


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["password-reset"],
        summary="Request a password reset code",
        description=(
            "Step 1 of 2. Same response for unknown accounts and mail delivery "
            "failures. Requires CSRF."
        ),
        auth=[{"csrfHeader": []}],
        request=PasswordResetRequestSerializer,
        responses={
            200: RequestSentSerializer,
            400: ValidationErrorResponse,
            403: CsrfForbiddenSerializer,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordResetService.request_reset(
            serializer.validated_data["email"], get_client_ip(request)
        )
        return Response({"detail": MSG_CODE_SENT})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["password-reset"],
        summary="Confirm a new password",
        description=(
            "Step 2 of 2. Consumes the code and invalidates all existing sessions. "
            "Requires CSRF."
        ),
        auth=[{"csrfHeader": []}],
        request=PasswordResetConfirmSerializer,
        responses={
            200: PasswordResetSerializer,
            400: ValidationErrorResponse,
            403: CsrfForbiddenSerializer,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        limit_code_verification_attempts(get_client_ip(request))
        try:
            PasswordResetService.confirm_reset(**serializer.validated_data)
        except Exception:
            record_event("PASSWORD_RESET", "FAILURE")
            raise
        logout(request)
        record_event("PASSWORD_RESET", "SUCCESS")
        return Response({"detail": MSG_PASSWORD_RESET})
