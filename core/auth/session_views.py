from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.validators import ValidationError
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from core.auth.cookies import get_auth_cookie_name
from core.auth.serializers import UserSessionSerializer
from core.auth.services import SessionService
from core.models.user import UserSession
from core.shared.docs import (
    CannotDeactivateCurrentSessionSerializer,
    NotAuthenticatedSerializer,
    UserSessionDeactivatedSerializer,
    UserSessionNotFoundSerializer,
)
from core.shared.response_messages import (
    MSG_CANNOT_DEACTIVATE_CURRENT_SESSION,
    MSG_USER_SESSION_DEACTIVATED,
    MSG_USER_SESSION_NOT_FOUND,
)


class UserSessionsDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate a session",
        description="",
        request=None,
        responses={
            200: UserSessionDeactivatedSerializer,
            400: CannotDeactivateCurrentSessionSerializer,
            401: NotAuthenticatedSerializer,
            404: UserSessionNotFoundSerializer,
        },
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
            )
        ],
    )
    def delete(self, request, session_id):
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        current_session = None
        if raw_access_token:
            try:
                current_jti = str(AccessToken(raw_access_token).get("jti", ""))
                current_session = UserSession.objects.filter(
                    access_jti=current_jti, user=request.user
                ).first()
            except TokenError:
                pass
        if current_session and current_session.id == session_id:
            raise ValidationError({"detail": MSG_CANNOT_DEACTIVATE_CURRENT_SESSION})
        try:
            SessionService.deactivate_session(request.user, session_id)
            return Response(
                {"detail": MSG_USER_SESSION_DEACTIVATED}, status.HTTP_200_OK
            )
        except UserSession.DoesNotExist:
            raise NotFound(MSG_USER_SESSION_NOT_FOUND)


class UserSessionsGetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List active user sessions",
        description="Returns all active sessions of the requesting user. And, indicates which session is the current.",
        request=None,
        responses={
            200: UserSessionSerializer(many=True),
            401: NotAuthenticatedSerializer,
        },
    )
    def get(self, request):
        raw_access_token = request.COOKIES.get(get_auth_cookie_name())
        sessions = SessionService.get_active_sessions_with_current(
            request.user, raw_access_token
        )
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
