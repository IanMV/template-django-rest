from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.cookies import get_auth_cookie_name
from core.auth.serializers import UserSessionSerializer
from core.auth.services import SessionService
from core.shared.docs import (
    CannotDeactivateCurrentSessionSerializer,
    NotAuthenticatedSerializer,
    UserSessionDeactivatedSerializer,
    UserSessionNotFoundSerializer,
)
from core.shared.response_messages import MSG_USER_SESSION_DEACTIVATED


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
        SessionService.deactivate_other_session(
            request.user, session_id, request.COOKIES.get(get_auth_cookie_name())
        )
        return Response({"detail": MSG_USER_SESSION_DEACTIVATED}, status.HTTP_200_OK)


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
