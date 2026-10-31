from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.cookies import clear_auth_cookies
from core.email_change.serializers import (
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailChangeVerifySerializer,
)
from core.email_change.services import EmailChangeService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CodeIsValidSerializer,
    CsrfFailureExample,
    CsrfForbiddenSerializer,
    InvalidCodeExample,
    NewEmailChangedSerializer,
    NotAuthenticatedSerializer,
    RateLimitedExample,
    RequestSentSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import (
    MSG_CODE_SENT,
    MSG_CODE_VALID,
    MSG_EMAIL_CHANGED,
)


class EmailChangeRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["email-change"],
        summary="Request an email change code",
        description="Step 1 of 3: while authenticated, submit the new email address. A six-digit code is sent to the new address; send X-CSRFTOKEN.",
        request=EmailChangeRequestSerializer,
        examples=[
            OpenApiExample(
                "New email", value={"new_email": "new@example.com"}, request_only=True
            ),
            OpenApiExample(
                "Email already in use",
                value={"new_email": "This e-mail is already in use."},
                response_only=True,
                status_codes=["400"],
            ),
            CsrfFailureExample,
            RateLimitedExample,
        ],
        responses={
            200: RequestSentSerializer,
            400: ValidationErrorResponse,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailChangeService.request_change(
            user=request.user,
            new_email=serializer.validated_data["new_email"],
            ip_address=get_client_ip(request),
        )
        return Response({"detail": MSG_CODE_SENT}, status=status.HTTP_200_OK)


class EmailChangeVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["email-change"],
        summary="Verify the new email code",
        description="Step 2 of 3: verify the six-digit code without consuming it. Requires the access cookie and X-CSRFTOKEN.",
        request=EmailChangeVerifySerializer,
        examples=[
            OpenApiExample(
                "Verify email change", value={"code": "123456"}, request_only=True
            ),
            InvalidCodeExample,
            CsrfFailureExample,
        ],
        responses={
            200: CodeIsValidSerializer,
            400: ValidationErrorResponse,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request):
        serializer = EmailChangeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailChangeService.verify_code(
            user=request.user, code=serializer.validated_data["code"]
        )
        return Response({"detail": MSG_CODE_VALID}, status=status.HTTP_200_OK)


class EmailChangeConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["email-change"],
        summary="Confirm the new email",
        description="Step 3 of 3: send the code and current password. Success changes the email, revokes all sessions and clears access/refresh cookies; log in again with the new email.",
        request=EmailChangeConfirmSerializer,
        examples=[
            OpenApiExample(
                "Confirm email change",
                value={"code": "123456", "password": "current-password"},
                request_only=True,
            ),
            InvalidCodeExample,
            CsrfFailureExample,
        ],
        responses={
            200: NewEmailChangedSerializer,
            400: ValidationErrorResponse,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailChangeService.confirm_change(
            user=request.user,
            code=serializer.validated_data["code"],
            current_password=serializer.validated_data["password"],
        )
        response = Response({"detail": MSG_EMAIL_CHANGED}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response
