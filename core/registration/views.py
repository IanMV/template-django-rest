from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.rate_limit import limit_code_verification_attempts
from core.registration.serializers import (
    RegistrationConfirmSerializer,
    RegistrationRequestSerializer,
    RegistrationVerifySerializer,
)
from core.registration.services import RegistrationService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CodeIsValidSerializer,
    InvalidCodeExample,
    RateLimitedExample,
    RequestSentSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    UserCreatedSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import (
    MSG_CODE_SENT,
    MSG_CODE_VALID,
    MSG_USER_CREATED,
)


class RegistrationRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["registration"],
        summary="Request a registration code",
        description="Step 1 of 3: submit an email. Existing active accounts receive a security notice instead of a code; the response is identical. Request again after the cooldown to replace an expired code.",
        request=RegistrationRequestSerializer,
        examples=[
            OpenApiExample(
                "Registration email",
                value={"email": "person@example.com"},
                request_only=True,
            ),
            RateLimitedExample,
        ],
        responses={
            201: RequestSentSerializer,
            400: ValidationErrorResponse,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = RegistrationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        RegistrationService.request_registration(
            email=serializer.validated_data["email"],
            ip_address=get_client_ip(request),
        )
        return Response({"detail": MSG_CODE_SENT}, status.HTTP_201_CREATED)


class RegistrationVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["registration"],
        summary="Verify the registration code",
        description="Step 2 of 3: check the six-digit email code without consuming it. Invalid attempts count toward the five-attempt limit.",
        request=RegistrationVerifySerializer,
        examples=[
            OpenApiExample(
                "Verify registration",
                value={"email": "person@example.com", "code": "123456"},
                request_only=True,
            ),
            InvalidCodeExample,
            RateLimitedExample,
        ],
        responses={
            200: CodeIsValidSerializer,
            400: ValidationErrorResponse,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = RegistrationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        limit_code_verification_attempts(get_client_ip(request))
        RegistrationService.verify_code(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
        )
        return Response({"detail": MSG_CODE_VALID}, status.HTTP_200_OK)


class RegistrationConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["registration"],
        summary="Confirm registration",
        description="Step 3 of 3: send the same email/code with a name and password. Success creates an active user and consumes the code; no authentication cookies are set.",
        request=RegistrationConfirmSerializer,
        examples=[
            OpenApiExample(
                "Confirm registration",
                value={
                    "email": "person@example.com",
                    "code": "123456",
                    "name": "Example Person",
                    "password": "StrongPass!4693$",
                },
                request_only=True,
            ),
            InvalidCodeExample,
            RateLimitedExample,
        ],
        responses={
            200: UserCreatedSerializer,
            400: ValidationErrorResponse,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = RegistrationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        limit_code_verification_attempts(get_client_ip(request))
        RegistrationService.confirm_registration(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            name=serializer.validated_data["name"],
            password=serializer.validated_data["password"],
        )
        return Response({"detail": MSG_USER_CREATED}, status.HTTP_200_OK)
