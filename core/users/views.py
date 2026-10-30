from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.cookies import clear_auth_cookies
from core.auth.services import SessionService
from core.shared.docs import (
    NotAuthenticatedSerializer,
    UserDeactivatedSerializer,
    UserRevokedAllSessionsSerializer,
)
from core.shared.response_messages import (
    MSG_USER_DEACTIVATED,
    MSG_USER_REVOKED_ALL_SESSIONS,
)
from core.users.serializers import UserListRetrieveSerializer
from core.users.services import UserService


class RevokeAllSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Revoke all active sessions",
        description="Instantly revokes all active sessions for the requesting user across all devices by blacklisting all outstanding refresh tokens and setting all session records to inactive.",
        request=None,
        responses={
            200: UserRevokedAllSessionsSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def post(self, request):
        SessionService.revoke_all_sessions(request.user)
        response = Response({"detail": MSG_USER_REVOKED_ALL_SESSIONS}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response


class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user profile",
        description="Retrieves the profile information for the currently authenticated user.",
        responses={
            200: UserListRetrieveSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def get(self, request):
        serializer = UserListRetrieveSerializer(request.user)
        return Response(serializer.data, status.HTTP_200_OK)


class UserListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List users",
        description="Retrieves a list of users registered in the system based on the authorization rules evaluated in the service layer.",
        responses={
            200: UserListRetrieveSerializer(many=True),
            401: NotAuthenticatedSerializer,
        },
    )
    def get(self, request):
        users = UserService.list_users(requesting_user=request.user)
        serializer = UserListRetrieveSerializer(users, many=True)
        return Response(serializer.data, status.HTTP_200_OK)


class DeactivateSelfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate own user account",
        description="Deactivates the authenticated user's account, revoking all active sessions and preventing subsequent authentication attempts.",
        request=None,
        responses={
            200: UserDeactivatedSerializer,
            401: NotAuthenticatedSerializer,
        },
    )
    def post(self, request):
        UserService.deactivate_user(request.user)
        response = Response({"detail": MSG_USER_DEACTIVATED}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response
