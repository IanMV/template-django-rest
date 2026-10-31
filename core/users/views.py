from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auth.cookies import clear_auth_cookies
from core.auth.services import SessionService
from core.shared.docs import (
    CsrfFailureExample,
    CsrfForbiddenSerializer,
    ForbiddenSerializer,
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
        tags=["sessions"],
        summary="Revoke all active sessions",
        description="Instantly revokes all active sessions for the requesting user across all devices by blacklisting all outstanding refresh tokens and setting all session records to inactive.",
        request=None,
        examples=[CsrfFailureExample],
        responses={
            200: UserRevokedAllSessionsSerializer,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request):
        SessionService.revoke_all_sessions(request.user)
        response = Response(
            {"detail": MSG_USER_REVOKED_ALL_SESSIONS}, status.HTTP_200_OK
        )
        clear_auth_cookies(response)
        return response


class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["user"],
        summary="Get current user profile",
        description="Retrieves the profile information for the currently authenticated user.",
        responses={
            200: UserListRetrieveSerializer,
            401: NotAuthenticatedSerializer,
        },
        request=None,
    )
    def get(self, request):
        serializer = UserListRetrieveSerializer(request.user)
        return Response(serializer.data, status.HTTP_200_OK)


class UserListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class UserListView(APIView):
    permission_classes = [IsAdminUser]
    pagination_class = UserListPagination

    @extend_schema(
        tags=["user"],
        summary="List users",
        description="Staff-only paginated list of active users.",
        responses={
            200: UserListRetrieveSerializer(many=True),
            401: NotAuthenticatedSerializer,
            403: ForbiddenSerializer,
        },
        request=None,
    )
    def get(self, request):
        users = UserService.list_users()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(users, request, view=self)
        serializer = UserListRetrieveSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class DeactivateSelfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["user"],
        summary="Deactivate own user account",
        description="Deactivates the authenticated user's account, revoking all active sessions and preventing subsequent authentication attempts.",
        request=None,
        examples=[CsrfFailureExample],
        responses={
            200: UserDeactivatedSerializer,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
        },
    )
    def post(self, request):
        UserService.deactivate_user(request.user)
        response = Response({"detail": MSG_USER_DEACTIVATED}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response
