from functools import wraps

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.serializers.custom_user import (
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailChangeVerifySerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    RegistrationConfirmSerializer,
    RegistrationRequestSerializer,
    RegistrationVerifySerializer,
    UserListRetrieveSerializer,
    UserPatchSerializer,
)

User = get_user_model()


def any_user_action(func):
    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    return wrapper


def specific_user_action(func):
    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.save(owner=request.user)

    return wrapper


class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = User.objects.all()
    http_method_names = ("get", "post", "patch", "delete")
    permission_classes = [AllowAny]

    # TODO: specify permissions for each action in view
    # def get_permissions(self):
    #     if self.action in {
    #         "create",
    #         "password_reset_request",
    #         "password_reset_confirm",
    #         "password_reset_verify",
    #         "email_verification_confirm",
    #         "email_verification_verify",
    #         "login",
    #     }:
    #         permission_classes = [AllowAny]
    #     else:
    #         permission_classes = [IsAuthenticated, IsUserOwner]
    #     return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        serializers_map = {
            "retrieve": UserListRetrieveSerializer,
            "list": UserListRetrieveSerializer,
            "registration_request": RegistrationRequestSerializer,
            "registration_verify": RegistrationVerifySerializer,
            "registration_confirm": RegistrationConfirmSerializer,
            "partial_update": UserPatchSerializer,
            "password_reset_request": PasswordResetRequestSerializer,
            "password_reset_confirm": PasswordResetConfirmSerializer,
            "password_reset_verify": PasswordResetVerifySerializer,
            "email_change_request": EmailChangeRequestSerializer,
            "email_change_confirm": EmailChangeConfirmSerializer,
            "email_change_verify": EmailChangeVerifySerializer,
            "login": LoginSerializer,
            "logout": LogoutSerializer,
        }
        return serializers_map.get(self.action, UserListRetrieveSerializer)

    def get_queryset(self):
        queryset = User.objects.all()
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset
        if self.action != "list" and user.is_authenticated:
            return queryset.filter(Q(is_active=True) | Q(pk=user.pk))
        return queryset.filter(is_active=True)

    @extend_schema(description="Deactivate a user from the database by ID")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"detail": "User successfully deactivated."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(description="Step 1: Request registration code")
    @action(detail=False, methods=["post"], url_path="registration-request")
    @any_user_action
    def registration_request(self, request):
        pass

    @extend_schema(description="Step 2: Verify registration code")
    @action(detail=False, methods=["post"], url_path="registration-verify")
    @any_user_action
    def registration_verify(self, request):
        pass

    @extend_schema(description="Step 3: Complete registration")
    @action(detail=False, methods=["post"], url_path="registration-confirm")
    @any_user_action
    def registration_confirm(self, request):
        pass

    @extend_schema(description="Retrieve a user from the database by ID")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(description="Update a user from the database by ID")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @any_user_action
    @extend_schema(description="Step 1: Request password reset code")
    @action(detail=False, methods=["post"], url_path="password-reset-request")
    def password_reset_request(self, request):
        pass

    @any_user_action
    @extend_schema(description="Step 2: Verify password reset code")
    @action(detail=False, methods=["post"], url_path="password-reset-verify")
    def password_reset_verify(self, request):
        pass

    @any_user_action
    @extend_schema(description="Step 3:Confirm password reset")
    @action(detail=False, methods=["post"], url_path="password-reset-confirm")
    def password_reset_confirm(self, request):
        pass

    @specific_user_action
    @extend_schema(description="Step 1: Request e-mail change")
    @action(detail=False, methods=["post"], url_path="email-change-request")
    def email_change_request(self, request):
        pass

    @any_user_action
    @extend_schema(description="Step 2: Verify e-mail change code")
    @action(detail=False, methods=["post"], url_path="email-change-verify")
    def email_change_verify(self, request):
        pass

    @specific_user_action
    @extend_schema(description="Step 3: Confirm e-mail change")
    @action(detail=False, methods=["post"], url_path="email-change-confirm")
    def email_change_confirm(self, request):
        pass

    @extend_schema(description="Login to the system", responses={200: None, 401: None})
    @action(detail=False, methods=["post"], url_path="login")
    def login(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return Response({"detail": "Successful login."})
        return Response(
            {"detail": "Invalid credentials."}, status.HTTP_401_UNAUTHORIZED
        )

    @extend_schema(description="Logout from the system", responses={200: None})
    @action(detail=False, methods=["post"], url_path="logout")
    def logout(self, request):
        logout(request)
        return Response({"detail": "Successful logout."})
