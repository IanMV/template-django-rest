from django.conf import settings
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
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken, UntypedToken
from user_agents import parse

from core.audit.services import record_event
from core.auth.rate_limit import limit_login_attempts, reset_login_attempts
from core.auth.session_cache import invalidate_sessions
from core.models import User, UserSession
from core.shared.response_messages import (
    MSG_CANNOT_DEACTIVATE_CURRENT_SESSION,
    MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN,
    MSG_NO_REFRESH_TOKEN_PROVIDED,
    MSG_SESSION_REVOKED_OR_INACTIVE,
    MSG_USER_SESSION_NOT_FOUND,
)


def require_unchanged_user(previous, current):
    if (
        current is None
        or not current.is_active
        or current.password != previous.password
        or current.email != previous.email
    ):
        raise AuthenticationFailed()


class SessionService:
    @staticmethod
    def refresh_expiry(session, now):
        inactivity = (
            settings.SESSION_REMEMBERED_INACTIVITY_LIFETIME
            if session.remember_me
            else settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        )
        absolute = (
            settings.SESSION_REMEMBERED_ABSOLUTE_LIFETIME
            if session.remember_me
            else settings.SESSION_ABSOLUTE_LIFETIME
        )
        return min(now + inactivity, session.created_at + absolute)

    @staticmethod
    def refresh_tokens(refresh_token_str, serializer_factory, request=None):
        if not refresh_token_str:
            raise AuthenticationFailed(MSG_NO_REFRESH_TOKEN_PROVIDED)
        try:
            old_token = RefreshToken(refresh_token_str)
            old_jti = str(old_token.get("jti", ""))
        except TokenError as exc:
            SessionService.revoke_reused_refresh(refresh_token_str, request=request)
            raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN) from exc

        try:
            return SessionService._rotate_refresh(
                old_token, old_jti, refresh_token_str, serializer_factory, request
            )
        except AuthenticationFailed:
            # A token validated before a concurrent rotation may now be blacklisted.
            SessionService.revoke_reused_refresh(refresh_token_str, request=request)
            raise
    @staticmethod
    def _rotate_refresh(old_token, old_jti, refresh_token_str, serializer_factory, request):
        expired = False
        with transaction.atomic():
            User.objects.select_for_update(no_key=True).get(pk=old_token["user_id"])
            session = (
                UserSession.objects.select_for_update()
                .filter(refresh_jti=old_jti, is_active=True)
                .first()
            )
            if not session:
                raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
            if (
                old_token.get("session_id") not in (None, session.pk)
                or str(old_token.get("user_id", "")) != str(session.user_id)
            ):
                raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
            now = timezone.now()
            expiry = SessionService.refresh_expiry(session, now)
            if now >= expiry:
                SessionService.deactivate_session(session.user, session.pk)
                expired = True
            else:
                serializer = serializer_factory(data={"refresh": refresh_token_str})
                try:
                    serializer.is_valid(raise_exception=True)
                except TokenError as exc:
                    raise InvalidToken(exc.args[0]) from exc

                response_data = serializer.validated_data
                if not response_data.get("access") or not response_data.get("refresh"):
                    raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN)
                new_refresh = RefreshToken(response_data["refresh"])
                new_refresh["session_id"] = session.pk
                new_refresh.set_exp(from_time=now, lifetime=expiry - now)
                new_access = new_refresh.access_token
                new_access.set_exp(
                    from_time=now,
                    lifetime=min(
                        settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], expiry - now
                    ),
                )
                access = str(new_access)
                refresh = str(new_refresh)
                OutstandingToken.objects.filter(jti=str(new_refresh["jti"])).update(
                    token=refresh, expires_at=expiry
                )
                if not SessionService.update_session_jtis(
                    old_refresh_jti=old_jti,
                    new_access_jti=str(new_access["jti"]),
                    new_refresh_jti=str(new_refresh["jti"]),
                ):
                    raise AuthenticationFailed(MSG_SESSION_REVOKED_OR_INACTIVE)
                invalidate_sessions([session.pk])
        if expired:
            if request:
                record_event(request, session.user, "SESSION_ABSOLUTE_EXPIRED", "FAILURE", {"session_id": session.pk})
            raise InvalidToken(MSG_INVALID_OR_EXPIRED_REFRESH_TOKEN)
        return {
            "access": access,
            "refresh": refresh,
            "access_exp": new_access["exp"],
            "refresh_exp": new_refresh["exp"],
            "user": session.user,
            "session_id": session.pk,
        }

    @staticmethod
    def revoke_reused_refresh(raw_token, request=None):
        try:
            token = UntypedToken(raw_token)
        except TokenError:
            return
        session_id = token.get("session_id")
        if (
            token.get("token_type") != "refresh"
            or type(session_id) is not int
            or session_id <= 0
        ):
            return
        old_jti = str(token.get("jti", ""))
        if not BlacklistedToken.objects.filter(
            token__jti=old_jti, token__user_id=token.get("user_id")
        ).exists():
            return
        with transaction.atomic():
            User.objects.select_for_update(no_key=True).get(pk=token["user_id"])
            session = (
                UserSession.objects.select_for_update()
                .filter(pk=session_id, user_id=token.get("user_id"), is_active=True)
                .first()
            )
            if session and session.refresh_jti != old_jti:
                SessionService.deactivate_session(session.user, session.pk)
                user = session.user
            else:
                user = None
        if user and request:
            record_event(request, user, "REFRESH_REUSE", "BLOCKED", {"session_id": session_id})

    @staticmethod
    def logout_user(user, token):
        SessionService.deactivate_session_by_access_jti(user, str(token["jti"]))

    @staticmethod
    def deactivate_other_session(user, session_id, token):
        current_id = token.get("session_id")
        if current_id is None:
            current_id = UserSession.objects.filter(
                access_jti=str(token["jti"]), user=user
            ).values_list("pk", flat=True).first()
        if current_id == session_id:
            raise ValidationError({"detail": MSG_CANNOT_DEACTIVATE_CURRENT_SESSION})
        try:
            SessionService.deactivate_session(user, session_id)
        except UserSession.DoesNotExist as exc:
            raise NotFound(MSG_USER_SESSION_NOT_FOUND) from exc

    @staticmethod
    def get_active_sessions_with_current(user, token):
        sessions = UserSession.objects.filter(user=user, is_active=True).order_by(
            "-last_activity", "-created_at"
        )
        current_access_jti = str(token["jti"])

        for session in sessions:
            session.current = bool(
                current_access_jti and str(session.access_jti) == current_access_jti
            )

        return sessions

    @staticmethod
    def deactivate_session(user, session_id):
        with transaction.atomic():
            User.objects.select_for_update(no_key=True).get(pk=user.pk)
            session = (
                UserSession.objects.select_for_update()
                .filter(id=session_id, user=user)
                .first()
            )
            if not session:
                raise UserSession.DoesNotExist(MSG_USER_SESSION_NOT_FOUND)
            if session.refresh_jti:
                outstanding_token = OutstandingToken.objects.filter(
                    jti=session.refresh_jti
                ).first()
                if outstanding_token:
                    BlacklistedToken.objects.get_or_create(token=outstanding_token)

            session.is_active = False
            session.save(update_fields=["is_active"])
            invalidate_sessions([session.pk])

    @staticmethod
    def deactivate_session_by_access_jti(user, access_jti):
        with transaction.atomic():
            User.objects.select_for_update(no_key=True).get(pk=user.pk)
            session = (
                UserSession.objects.select_for_update()
                .filter(access_jti=access_jti, user=user)
                .first()
            )
            if session:
                if session.refresh_jti:
                    outstanding_token = OutstandingToken.objects.filter(
                        jti=session.refresh_jti
                    ).first()
                    if outstanding_token:
                        BlacklistedToken.objects.get_or_create(token=outstanding_token)

                session.is_active = False
                session.save(update_fields=["is_active"])
                invalidate_sessions([session.pk])

    @staticmethod
    def revoke_all_sessions(user):
        with transaction.atomic():
            User.objects.select_for_update(no_key=True).get(pk=user.pk)
            tokens = OutstandingToken.objects.filter(user=user)
            BlacklistedToken.objects.bulk_create(
                [BlacklistedToken(token=token) for token in tokens],
                ignore_conflicts=True,
            )
            sessions = UserSession.objects.filter(user=user, is_active=True)
            session_ids = list(sessions.values_list("pk", flat=True))
            sessions.update(is_active=False)
            invalidate_sessions(session_ids)

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
        email, password, user_agent_string, ip_address, raw_access_token=None, remember_me=False
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
        user_agent = parse(user_agent_string)

        with transaction.atomic():
            user_ids = [user.pk]
            if previous_session:
                user_ids.append(previous_session.user_id)
            locked_users = list(
                User.objects.select_for_update(no_key=True)
                .filter(pk__in=user_ids)
                .order_by("pk")
            )
            current = next((item for item in locked_users if item.pk == user.pk), None)
            require_unchanged_user(user, current)
            user = current
            refresh = RefreshToken.for_user(user)
            access = refresh.access_token
            jti_refresh = str(refresh["jti"])
            candidate_ids = set(
                UserSession.objects.select_for_update()
                .filter(
                    user=user,
                    device_name=f"{user_agent.browser.family} on {user_agent.os.family}",
                    ip_address=ip_address,
                    is_active=True,
                )
                .values_list("pk", flat=True)
            )
            if previous_session:
                candidate_ids.add(previous_session.pk)
            revoked = list(
                UserSession.objects.select_for_update().filter(
                    pk__in=candidate_ids, is_active=True
                )
            )
            replaced_ids = [item.pk for item in revoked]
            refresh_jtis = [item.refresh_jti for item in revoked if item.refresh_jti]
            outstanding = OutstandingToken.objects.filter(jti__in=refresh_jtis)
            BlacklistedToken.objects.bulk_create(
                [BlacklistedToken(token=token) for token in outstanding],
                ignore_conflicts=True,
            )
            if replaced_ids:
                UserSession.objects.filter(pk__in=replaced_ids).update(is_active=False)
                invalidate_sessions(replaced_ids)
            session = UserSession.objects.create(
                user=user,
                device_name=f"{user_agent.browser.family} on {user_agent.os.family}",
                ip_address=ip_address,
                access_jti=str(access["jti"]),
                refresh_jti=jti_refresh,
                remember_me=remember_me,
            )
            refresh["session_id"] = session.pk
            access["session_id"] = session.pk
            now = timezone.now()
            expiry = SessionService.refresh_expiry(session, now)
            refresh.set_exp(from_time=now, lifetime=expiry - now)
            access.set_exp(
                from_time=now,
                lifetime=min(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], expiry - now),
            )
            OutstandingToken.objects.filter(jti=jti_refresh).update(
                token=str(refresh), expires_at=expiry
            )
        reset_login_attempts(email, ip_address)

        return {
            "refresh": str(refresh),
            "access": str(access),
            "refresh_exp": refresh["exp"],
            "access_exp": access["exp"],
            "user": user,
            "session_id": session.pk,
        }
