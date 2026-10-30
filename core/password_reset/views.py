from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.password_reset.serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
)
from core.password_reset.services import PasswordResetService
from core.shared.docs import (
    CodeIsValidSerializer,
    InvalidCodeExample,
    PasswordResetSerializer,
    RateLimitedExample,
    RequestSentSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import (
    MSG_CODE_SENT,
    MSG_CODE_VALID,
    MSG_PASWORD_RESET,
)


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["password-reset"],
        summary="Request a password reset code",
        description="Step 1 of 3: enter the account email. For privacy the same response is returned for unknown addresses; active accounts receive a six-digit code.",
        request=PasswordResetRequestSerializer,
        examples=[
            OpenApiExample(
                "Account email",
                value={"email": "person@example.com"},
                request_only=True,
            ),
            RateLimitedExample,
        ],
        responses={
            200: RequestSentSerializer,
            400: ValidationErrorResponse,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordResetService.request_reset(
            serializer.validated_data["email"], request.META.get("REMOTE_ADDR")
        )

        return Response(
            {"detail": MSG_CODE_SENT},
            status.HTTP_200_OK,
        )


class PasswordResetVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["password-reset"],
        summary="Verify the password reset code",
        description="Step 2 of 3: check the email and six-digit code without consuming it. Wrong codes count toward the five-attempt limit.",
        request=PasswordResetVerifySerializer,
        examples=[
            OpenApiExample(
                "Verify reset",
                value={"email": "person@example.com", "code": "123456"},
                request_only=True,
            ),
            InvalidCodeExample,
        ],
        responses={
            200: CodeIsValidSerializer,
            400: ValidationErrorResponse,
        },
    )
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordResetService.verify_code(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
        )

        return Response({"detail": MSG_CODE_VALID}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["password-reset"],
        summary="Confirm the new password",
        description="Step 3 of 3: send email, code and a new password. Success consumes the code and revokes existing sessions; this endpoint does not create authentication cookies.",
        request=PasswordResetConfirmSerializer,
        examples=[
            OpenApiExample(
                "Confirm reset",
                value={
                    "email": "person@example.com",
                    "code": "123456",
                    "new_password": "StrongPass!4693$",
                },
                request_only=True,
            ),
            InvalidCodeExample,
        ],
        responses={
            200: PasswordResetSerializer,
            400: ValidationErrorResponse,
        },
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PasswordResetService.confirm_reset(
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            new_password=serializer.validated_data["new_password"],
        )

        return Response({"detail": MSG_PASWORD_RESET}, status.HTTP_200_OK)
