from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.rate_limit import limit_code_verification_attempts
from core.registration.serializers import RegistrationConfirmSerializer, RegistrationRequestSerializer
from core.registration.services import RegistrationService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CsrfForbiddenSerializer,
    RequestSentSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    UserCreatedSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import MSG_CODE_SENT, MSG_USER_CREATED


class RegistrationRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["registration"],
        summary="Request a registration code",
        description="Step 1 of 2. Existing active accounts receive a security notice instead of a code. Requires CSRF.",
        auth=[{"csrfHeader": []}],
        request=RegistrationRequestSerializer,
        responses={201: RequestSentSerializer, 400: ValidationErrorResponse, 403: CsrfForbiddenSerializer, 429: ThrottledSerializer, 503: ServiceUnavailableSerializer},
    )
    def post(self, request):
        serializer = RegistrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        RegistrationService.request_registration(serializer.validated_data["email"], get_client_ip(request))
        return Response({"detail": MSG_CODE_SENT}, status=status.HTTP_201_CREATED)


class RegistrationConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["registration"],
        summary="Confirm registration",
        description="Step 2 of 2. Validates and consumes the code, then activates the account. Does not log in. Requires CSRF.",
        auth=[{"csrfHeader": []}],
        request=RegistrationConfirmSerializer,
        responses={200: UserCreatedSerializer, 400: ValidationErrorResponse, 403: CsrfForbiddenSerializer, 429: ThrottledSerializer, 503: ServiceUnavailableSerializer},
    )
    def post(self, request):
        serializer = RegistrationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        limit_code_verification_attempts(get_client_ip(request))
        RegistrationService.confirm_registration(**serializer.validated_data)
        return Response({"detail": MSG_USER_CREATED})
