from django.middleware import csrf
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from core.auth.authenticate import enforce_csrf
from core.auth.cookies import (
    clear_auth_cookies,
    clear_legacy_refresh_cookie,
    get_auth_cookie_kwargs,
    get_auth_cookie_name,
)
from core.auth.serializers import LoginSerializer
from core.auth.services import AuthService, SessionService
from core.shared.client_ip import get_client_ip
from core.shared.docs import (
    CsrfFailureExample,
    CsrfForbiddenSerializer,
    IncorrectAuthenticationsCredentialsSerializer,
    InvalidOrExpiredRefreshTokenSerializer,
    LoginSuccessfulSerializer,
    LogoutSuccessfulSerializer,
    NotAuthenticatedSerializer,
    RefreshTokensSuccessfulSerializer,
    ThrottledSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import (
    MSG_LOGIN_SUCCESSFUL,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_REFRESH_TOKENS_SUCCESSFUL,
)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(exc, AuthenticationFailed) and response.status_code == 403:
            response.status_code = 401
        return response

    @extend_schema(
        tags=["auth"],
        summary="Get the CSRF cookie",
        description="Step 1: call this before login. The empty response sets the readable csrftoken cookie; send its value as X-CSRFTOKEN on POST /api/login/.",
        request=None,
        auth=[],
        responses={
            204: OpenApiResponse(
                response=None, description="No body; Set-Cookie: csrftoken."
            )
        },
    )
    def get(self, request):
        csrf.get_token(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["auth"],
        summary="Log in and set authentication cookies",
        description="Step 2: after GET /api/login/, send the CSRF header and email/password. A successful response contains only detail and sets HttpOnly access_token and refresh_token cookies (the access cookie name follows SIMPLE_JWT.AUTH_COOKIE). Existing matching sessions are revoked. Do not enter a JWT in Swagger's cookie authorization field; use the browser cookies.",
        auth=[{"csrfHeader": []}],
        examples=[
            OpenApiExample(
                "Login credentials",
                value={"email": "person@example.com", "password": "your-password"},
                request_only=True,
            ),
            OpenApiExample(
                "Invalid credentials",
                value={"detail": "Incorrect authentication credentials."},
                response_only=True,
                status_codes=["401"],
            ),
            CsrfFailureExample,
        ],
        request=LoginSerializer,
        responses={
            200: LoginSuccessfulSerializer,
            400: ValidationErrorResponse,
            401: IncorrectAuthenticationsCredentialsSerializer,
            403: CsrfForbiddenSerializer,
            429: ThrottledSerializer,
        },
    )
    def post(self, request):
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_data = AuthService.login_user(
            email=serializer.validated_data.get("email"),
            password=serializer.validated_data.get("password"),
            user_agent_string=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=get_client_ip(request),
            raw_access_token=request.COOKIES.get(get_auth_cookie_name()),
        )

        response = Response({"detail": MSG_LOGIN_SUCCESSFUL}, status.HTTP_200_OK)
        access_cookie_kwargs = get_auth_cookie_kwargs(is_refresh=False)
        refresh_cookie_kwargs = get_auth_cookie_kwargs(is_refresh=True)

        response.set_cookie(
            get_auth_cookie_name(), token_data["access"], **access_cookie_kwargs
        )
        response.set_cookie(
            "refresh_token", token_data["refresh"], **refresh_cookie_kwargs
        )
        clear_legacy_refresh_cookie(response)
        csrf.get_token(request)

        return response


class CustomTokenRefreshView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if response.status_code == 401:
            clear_auth_cookies(response)
        return response

    @extend_schema(
        tags=["auth"],
        summary="Rotate authentication cookies",
        description="Step 3: after login, send the refresh_token cookie and CSRF header. No JSON request body or tokens in the response; Set-Cookie replaces both access and refresh cookies. This works even after the access token expires.",
        auth=[{"refreshCookie": [], "csrfHeader": []}],
        request=None,
        examples=[
            OpenApiExample(
                "Expired refresh cookie",
                value={"detail": "Invalid or expired refresh token."},
                response_only=True,
                status_codes=["401"],
            ),
            CsrfFailureExample,
        ],
        responses={
            200: RefreshTokensSuccessfulSerializer,
            401: OpenApiResponse(
                response=InvalidOrExpiredRefreshTokenSerializer,
                description="Missing, expired, invalid or revoked refresh cookie. Missing/revoked cookies return detail only; invalid tokens may include code.",
            ),
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request, *args, **kwargs):
        enforce_csrf(request)
        token_data = SessionService.refresh_tokens(
            request.COOKIES.get("refresh_token"), self.get_serializer
        )
        response = Response(
            {"detail": MSG_REFRESH_TOKENS_SUCCESSFUL}, status.HTTP_200_OK
        )
        response.set_cookie(
            get_auth_cookie_name(),
            token_data["access"],
            **get_auth_cookie_kwargs(is_refresh=False),
        )
        response.set_cookie(
            "refresh_token",
            token_data["refresh"],
            **get_auth_cookie_kwargs(is_refresh=True),
        )
        clear_legacy_refresh_cookie(response)

        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Log out the user current session",
        description="Revoke the current session and clear the access/refresh cookies. Send X-CSRFTOKEN with the browser cookies.",
        request=None,
        examples=[CsrfFailureExample],
        responses={
            200: LogoutSuccessfulSerializer,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request):
        SessionService.logout_user(
            request.user, request.auth
        )
        response = Response({"detail": MSG_LOGOUT_SUCCESSFUL}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response
