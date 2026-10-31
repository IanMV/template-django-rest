from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit.services import record_event
from core.auth.cookies import clear_auth_cookies
from core.auth.services import SessionService
from core.shared.docs import (
    CsrfFailureExample,
    CsrfForbiddenSerializer,
    ForbiddenSerializer,
    InvalidPasswordExample,
    NotAuthenticatedSerializer,
    ReauthRateLimitedExample,
    ServiceUnavailableSerializer,
    ThrottledSerializer,
    UserDeactivatedSerializer,
    UserRevokedAllSessionsSerializer,
    ValidationErrorResponse,
)
from core.shared.response_messages import (
    MSG_USER_DEACTIVATED,
    MSG_USER_REVOKED_ALL_SESSIONS,
)
from core.users.serializers import DeactivateSelfSerializer, UserListRetrieveSerializer
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
        record_event(request, request.user, "SESSION_REVOKE", "SUCCESS", {"scope": "all"})
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
        record_event(request, request.user, "USER_LIST_ACCESS", "SUCCESS")
        return paginator.get_paginated_response(serializer.data)


class DeactivateSelfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["user"],
        summary="Deactivate own user account",
        description="Requires the current password. Deactivates the authenticated account and revokes all active sessions.",
        request=DeactivateSelfSerializer,
        examples=[InvalidPasswordExample, CsrfFailureExample, ReauthRateLimitedExample],
        responses={
            200: UserDeactivatedSerializer,
            400: ValidationErrorResponse,
            401: NotAuthenticatedSerializer,
            403: CsrfForbiddenSerializer,
            429: ThrottledSerializer,
            503: ServiceUnavailableSerializer,
        },
    )
    def post(self, request):
        serializer = DeactivateSelfSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        UserService.deactivate_user(request.user, serializer.validated_data["password"], request=request)
        record_event(request, request.user, "SESSION_REVOKE", "SUCCESS", {"scope": "all"})
        response = Response({"detail": MSG_USER_DEACTIVATED}, status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response
