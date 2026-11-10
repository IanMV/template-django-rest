from django.contrib.auth import logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.serializers import (
    CsrfSerializer,
    LoginResponseSerializer,
    LoginSerializer,
)
from core.auth.services import AuthService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CsrfForbiddenSerializer,
    IncorrectAuthenticationsCredentialsSerializer,
    LogoutSuccessfulSerializer,
    NotAuthenticatedSerializer,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import MSG_LOGIN_SUCCESSFUL, MSG_LOGOUT_SUCCESSFUL
from core.shared.security import record_event


@method_decorator(never_cache, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Get a CSRF token before any mutation",
        description=(
            "Call with credentials included. Keep csrfToken in memory and send it "
            "as X-CSRFTOKEN. No authentication credential is returned."
        ),
        auth=[],
        responses={200: CsrfSerializer},
    )
    def get(self, request):
        return Response({"csrfToken": get_token(request)})

    @extend_schema(
        tags=["auth"],
        summary="Log in for 24 hours",
        description=(
            "Requires X-CSRFTOKEN. Sets an HttpOnly session cookie and returns "
            "the rotated CSRF token. No refresh endpoint is needed."
        ),
        auth=[{"csrfHeader": []}],
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            400: ValidationErrorResponse,
            401: IncorrectAuthenticationsCredentialsSerializer,
            403: CsrfForbiddenSerializer,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AuthService.login_user(
                request,
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
                ip_address=get_client_ip(request),
            )
        except Exception:
            record_event("LOGIN", "FAILURE")
            raise
        record_event("LOGIN", "SUCCESS")
        return Response(
            {"detail": MSG_LOGIN_SUCCESSFUL, "csrfToken": get_token(request)}
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Log out the current session",
        request=None,
        responses={
            200: LogoutSuccessfulSerializer,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request):
        logout(request)
        record_event("LOGOUT", "SUCCESS")
        return Response({"detail": MSG_LOGOUT_SUCCESSFUL})
