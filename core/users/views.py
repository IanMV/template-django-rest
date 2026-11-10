from django.contrib.auth import logout
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    ValidationErrorResponse,
)
from core.shared.response_messages import (
    MSG_USER_DEACTIVATED,
)
from core.shared.security import record_event
from core.users.serializers import DeactivateSelfSerializer, UserListRetrieveSerializer
from core.users.services import UserService


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
        UserService.deactivate_user(request.user, serializer.validated_data["password"])
        logout(request)
        record_event("DEACTIVATE", "SUCCESS")
        return Response({"detail": MSG_USER_DEACTIVATED}, status.HTTP_200_OK)
