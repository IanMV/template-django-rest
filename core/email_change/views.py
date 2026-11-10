from django.contrib.auth import logout
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.rate_limit import limit_code_verification_attempts
from core.email_change.serializers import EmailChangeConfirmSerializer, EmailChangeRequestSerializer
from core.email_change.services import EmailChangeService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CsrfForbiddenSerializer,
    NewEmailChangedSerializer,
    NotAuthenticatedSerializer,
    RequestSentSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import MSG_CODE_SENT, MSG_EMAIL_CHANGED
from core.shared.security import record_event


class EmailChangeRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["email-change"],
        summary="Request an email change code",
        description="Step 1 of 2. Requires the current password. Sends a code to the new address.",
        request=EmailChangeRequestSerializer,
        responses={200: RequestSentSerializer, 400: ValidationErrorResponse, 401: NotAuthenticatedSerializer, 403: CsrfForbiddenSerializer, 429: ThrottledSerializer, 503: ServiceUnavailableSerializer},
    )
    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        EmailChangeService.request_change(
            user=request.user,
            new_email=serializer.validated_data["new_email"],
            current_password=serializer.validated_data["password"],
            ip_address=get_client_ip(request),
        )
        return Response({"detail": MSG_CODE_SENT})


class EmailChangeConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["email-change"],
        summary="Confirm an email change",
        description="Step 2 of 2. Requires the code and current password. Invalidates all sessions; log in again with the new email.",
        request=EmailChangeConfirmSerializer,
        responses={200: NewEmailChangedSerializer, 400: ValidationErrorResponse, 401: NotAuthenticatedSerializer, 403: CsrfForbiddenSerializer, 429: ThrottledSerializer, 503: ServiceUnavailableSerializer},
    )
    def post(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        limit_code_verification_attempts(get_client_ip(request))
        try:
            EmailChangeService.confirm_change(
                user=request.user,
                code=serializer.validated_data["code"],
                current_password=serializer.validated_data["password"],
            )
        except Exception:
            record_event("EMAIL_CHANGE", "FAILURE")
            raise
        logout(request)
        record_event("EMAIL_CHANGE", "SUCCESS")
        return Response({"detail": MSG_EMAIL_CHANGED})
