from django.db import transaction
from django.middleware import csrf
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from core.auth.authenticate import enforce_csrf
from core.auth.cookies import (
    clear_auth_cookies,
    get_auth_cookie_kwargs,
    get_auth_cookie_name,
)
from core.models.user import UserSession
from core.shared.response_messages import (
    MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN,
    MSG_LOGIN_SUCCESSFUL,
    MSG_LOGOUT_SUCCESSFUL,
    MSG_NO_REFRESH_TOKEN_PROVIDED,
    MSG_REFRESH_TOKENS_SUCCESSFUL,
    MSG_SESSION_REVOKED_OR_INACTIVE,
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

        previous_session = None
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        if raw_access_token:
            try:
                jti = str(AccessToken(raw_access_token).get("jti", ""))
                previous_session = UserSession.objects.filter(
                    access_jti=jti, is_active=True
                ).select_related("user").first()
            except TokenError:
                pass

        token_data = AuthService.login_user(
            email=serializer.validated_data.get("email"),
            password=serializer.validated_data.get("password"),
            user_agent_string=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        if previous_session:
            SessionService.deactivate_session(
                previous_session.user, previous_session.pk
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
        refresh_token_str = request.COOKIES.get("refresh_token")
        if not refresh_token_str:
            raise AuthenticationFailed(MSG_NO_REFRESH_TOKEN_PROVIDED)
        try:
            old_refresh_token = RefreshToken(refresh_token_str)
            old_jti = str(old_refresh_token.get("jti", ""))
        except TokenError:
            raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN)
        with transaction.atomic():
            session = UserSession.objects.select_for_update().filter(
                refresh_jti=old_jti, is_active=True
            ).first()
            if not session:
                raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
            data = {"refresh": refresh_token_str}
            serializer = self.get_serializer(data=data)
            try:
                serializer.is_valid(raise_exception=True)
            except TokenError as e:
                raise InvalidToken(e.args[0]) from e

            response_data = serializer.validated_data
            new_access_token = response_data.get("access")
            new_refresh_token = response_data.get("refresh")
            if not new_access_token or not new_refresh_token:
                raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN)
            new_access_jti = str(AccessToken(new_access_token).get("jti", ""))
            new_refresh_jti = str(RefreshToken(new_refresh_token).get("jti", ""))
            if not SessionService.update_session_jtis(
                old_refresh_jti=old_jti,
                new_access_jti=new_access_jti,
                new_refresh_jti=new_refresh_jti,
            ):
                raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
        response = Response(
            {"detail": MSG_REFRESH_TOKENS_SUCCESSFUL}, status.HTTP_200_OK
        )
        response.set_cookie(
            get_auth_cookie_name(),
            new_access_token,
            **get_auth_cookie_kwargs(is_refresh=False),
        )
        response.set_cookie(
            "refresh_token",
            new_refresh_token,
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
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        if raw_access_token:
            try:
                jti = str(AccessToken(raw_access_token).get("jti", ""))
                SessionService.deactivate_session_by_access_jti(request.user, jti)
            except TokenError:
                pass
        response = Response({"detail": MSG_LOGOUT_SUCCESSFUL}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response

