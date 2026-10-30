from django.middleware import csrf
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from core.auth.authenticate import enforce_csrf
from core.auth.cookies import (
    clear_auth_cookies,
    get_auth_cookie_kwargs,
    get_auth_cookie_name,
)
from core.auth.serializers import LoginSerializer
from core.auth.services import AuthService, SessionService
from core.shared.docs import (
    IncorrectAuthenticationsCredentialsSerializer,
    InvalidOrExpiredRefreshTokenSerializer,
    LoginSucessfulSerializer,
    LogoutSuccessfulSerializer,
    NotAuthenticatedSerializer,
    RefreshTokensSuccessfulSerializer,
)
from core.shared.response_messages import (
    MSG_LOGIN_SUCCESSFUL,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_REFRESH_TOKENS_SUCCESSFUL,
)

# TODO: add description and summary to all of views

# TODO: adicionar responses aos novos endpoints de resfresh e arrumar MSG_... deles nos erros (estão em português e sem gettext_lazy)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        csrf.get_token(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Authenticate user and set JWT tokens in the browser cookies",
        description="When a user makes a request, the default authentication class defined in the DRF settings is not applied; that is, anyone can perform the operation. When the login is successful, JWT cookies are set in the browser. Considering different cases:\n\nA - User is not yet logged in (no cookies in the browser):\nThe operation proceeds, verifying the credentials (responses below) and setting the cookies.\n\nB - The user is already logged in (already has cookies in the browser):\nThe operation also proceeds normally too, however, the access and refresh cookies set in the previous login are invalidated within the blacklist.",
        request=LoginSerializer,
        responses={
            200: LoginSucessfulSerializer,
            401: IncorrectAuthenticationsCredentialsSerializer,
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
            ip_address=request.META.get("REMOTE_ADDR"),
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
        csrf.get_token(request)

        return response


class CustomTokenRefreshView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Refresh the user session using refresh token setted in the user browser",
        request=LoginSerializer,
        responses={
            200: RefreshTokensSuccessfulSerializer,
            401: InvalidOrExpiredRefreshTokenSerializer,
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

        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Log out the user current session",
        description="Its purpose is to log the user out of their current session. It adds the refresh and access tokens defined in the user's browser to the blacklist table. It also instructs the browser to delete the cookies related to authentication.",
        request=None,
        responses={
            200: LogoutSuccessfulSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def post(self, request):
        SessionService.logout_user(
            request.user, request.COOKIES.get(get_auth_cookie_name())
        )
        response = Response({"detail": MSG_LOGOUT_SUCCESSFUL}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response
