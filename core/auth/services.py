from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, NotFound
from rest_framework.validators import ValidationError
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from user_agents import parse

from core.auth.rate_limit import limit_login_attempts, reset_login_attempts
from core.models.user import UserSession
from core.shared.response_messages import (
    MSG_CANNOT_DEACTIVATE_CURRENT_SESSION,
    MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN,
    MSG_NO_REFRESH_TOKEN_PROVIDED,
    MSG_SESSION_REVOKED_OR_INACTIVE,
    MSG_USER_SESSION_NOT_FOUND,
)


class SessionService:
    @staticmethod
    def refresh_tokens(refresh_token_str, serializer_factory):
        if not refresh_token_str:
            raise AuthenticationFailed(MSG_NO_REFRESH_TOKEN_PROVIDED)
        try:
            old_jti = str(RefreshToken(refresh_token_str).get("jti", ""))
        except TokenError as exc:
            raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN) from exc

        with transaction.atomic():
            session = (
                UserSession.objects.select_for_update()
                .filter(refresh_jti=old_jti, is_active=True)
                .first()
            )
            if not session:
                raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
            serializer = serializer_factory(data={"refresh": refresh_token_str})
            try:
                serializer.is_valid(raise_exception=True)
            except TokenError as exc:
                raise InvalidToken(exc.args[0]) from exc

            response_data = serializer.validated_data
            access = response_data.get("access")
            refresh = response_data.get("refresh")
            if not access or not refresh:
                raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN)
            if not SessionService.update_session_jtis(
                old_refresh_jti=old_jti,
                new_access_jti=str(AccessToken(access).get("jti", "")),
                new_refresh_jti=str(RefreshToken(refresh).get("jti", "")),
            ):
                raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
        return {"access": access, "refresh": refresh}

    @staticmethod
    def logout_user(user, raw_access_token):
        if raw_access_token:
            try:
                jti = str(AccessToken(raw_access_token).get("jti", ""))
                SessionService.deactivate_session_by_access_jti(user, jti)
            except TokenError:
                pass

    @staticmethod
    def deactivate_other_session(user, session_id, raw_access_token):
        if raw_access_token:
            try:
                current_jti = str(AccessToken(raw_access_token).get("jti", ""))
                current_session = UserSession.objects.filter(
                    access_jti=current_jti, user=user
                ).first()
                if current_session and current_session.id == session_id:
                    raise ValidationError(
                        {"detail": MSG_CANNOT_DEACTIVATE_CURRENT_SESSION}
                    )
            except TokenError:
                pass
        try:
            SessionService.deactivate_session(user, session_id)
        except UserSession.DoesNotExist as exc:
            raise NotFound(MSG_USER_SESSION_NOT_FOUND) from exc

    @staticmethod
    def get_active_sessions_with_current(user, raw_access_token):
        sessions = UserSession.objects.filter(user=user, is_active=True)
        current_access_jti = None

        if raw_access_token:
            try:
                current_access_jti = str(AccessToken(raw_access_token).get("jti", ""))
            except TokenError:
                pass

        for session in sessions:
            session.current = bool(
                current_access_jti and str(session.access_jti) == current_access_jti
            )

        return sessions

    @staticmethod
    def deactivate_session(user, session_id):
        session = UserSession.objects.get(id=session_id, user=user)
        try:
            if session.refresh_jti:
                outstanding_token = OutstandingToken.objects.get(
                    jti=session.refresh_jti
                )
                BlacklistedToken.objects.get_or_create(token=outstanding_token)
        except OutstandingToken.DoesNotExist:
            pass

        session.is_active = False
        session.save(update_fields=["is_active"])

    @staticmethod
    def deactivate_session_by_access_jti(user, access_jti):
        session = UserSession.objects.filter(access_jti=access_jti, user=user).first()

        if session:
            try:
                if session.refresh_jti:
                    outstanding_token = OutstandingToken.objects.get(
                        jti=session.refresh_jti
                    )
                    BlacklistedToken.objects.get_or_create(token=outstanding_token)
            except OutstandingToken.DoesNotExist:
                pass

            session.is_active = False
            session.save(update_fields=["is_active"])

    @staticmethod
    def revoke_all_sessions(user):
        tokens = OutstandingToken.objects.filter(user=user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)
        UserSession.objects.filter(user=user, is_active=True).update(is_active=False)

    @classmethod
    def update_session_jtis(
        cls, old_refresh_jti: str, new_access_jti: str, new_refresh_jti: str
    ):
        return UserSession.objects.filter(
            refresh_jti=old_refresh_jti, is_active=True
        ).update(
            access_jti=new_access_jti,
            refresh_jti=new_refresh_jti,
            last_activity=timezone.now(),
        )


class AuthService:
    @staticmethod
    def login_user(
        email, password, user_agent_string, ip_address, raw_access_token=None
    ):
        limit_login_attempts(email, ip_address)
        previous_session = None
        if raw_access_token:
            try:
                jti = str(AccessToken(raw_access_token).get("jti", ""))
                previous_session = (
                    UserSession.objects.filter(access_jti=jti, is_active=True)
                    .select_related("user")
                    .first()
                )
            except TokenError:
                pass
        user = authenticate(email=email, password=password)

        if not user or not user.is_active:
            raise AuthenticationFailed()
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        user_agent = parse(user_agent_string)
        jti_access = str(AccessToken(access_token).get("jti"))
        jti_refresh = str(RefreshToken(refresh_token).get("jti"))

        with transaction.atomic():
            sessions = UserSession.objects.select_for_update().filter(
                user=user,
                device_name=f"{user_agent.browser.family} on {user_agent.os.family}",
                ip_address=ip_address,
                is_active=True,
            )
            for session in sessions:
                SessionService.deactivate_session(user, session.pk)
            UserSession.objects.create(
                user=user,
                device_name=f"{user_agent.browser.family} on {user_agent.os.family}",
                ip_address=ip_address,
                access_jti=jti_access,
                refresh_jti=jti_refresh,
            )
        if previous_session:
            SessionService.deactivate_session(
                previous_session.user, previous_session.pk
            )

        reset_login_attempts(email, ip_address)

        return {
            "refresh": refresh_token,
            "access": access_token,
        }
