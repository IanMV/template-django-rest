import secrets

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from core.models.email_change import EmailChange
from core.models.password_reset import PasswordReset
from core.permissions.is_user import IsUserOwner
from core.serializers.custom_user import (
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailChangeVerifySerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    UserCreateSerializer,
    UserListRetrieveSerializer,
    UserPatchSerializer,
)
from core.utils.email_token_sender import send_email_token

User = get_user_model()


class UserViewSet(ModelViewSet):
    queryset = User.objects.all()
    http_method_names = ("get", "post", "patch", "delete")

    def get_permissions(self):
        if self.action in {
            "create",
            "password_reset_request",
            "password_reset_confirm",
            "password_reset_verify",
            "login",
        }:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated, IsUserOwner]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        serializers_map = {
            "retrieve": UserListRetrieveSerializer,
            "list": UserListRetrieveSerializer,
            "create": UserCreateSerializer,
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
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(
            {"detail": "User successfully deactivated."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(description="Create a new user")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(description="Retrieve a user from the database by ID")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(description="Update a user from the database by ID")
    def partial_update(self, request, *args, **kwargs):
        if any(field in request.data for field in ["email", "new_email", "password"]):
            return Response(
                {"detail": "It is not possible to change these fields directly."},
                status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(description="Request password reset code")
    @action(detail=False, methods=["post"])
    def password_reset_request(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email).first()
        if not user:
            return Response(
                {"detail": "If this e-mail exists, a code was sent."},
                status=status.HTTP_200_OK,
            )
        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            PasswordReset.objects.filter(user=user).delete()
            reset_code = PasswordReset(user=user)
            reset_code.set_code(raw_code)
            reset_code.save()
            send_email_token(user.email, raw_code, "Your password reset code")
        except Exception:
            transaction.set_rollback(True)
            return Response(
                {"detail": "Failed to send e-mail with code. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"detail": "If this e-mail exists, a code was sent."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(description="Confirm password reset")
    @action(detail=False, methods=["post"])
    def password_reset_confirm(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]
        user = User.objects.filter(email=email).first()
        reset_code = PasswordReset.objects.filter(user=user).first() if user else None
        if not reset_code:
            return Response(
                {"detail": "No reset request found for this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not reset_code.verify(code):
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        reset_code.mark_used()
        return Response(
            {"detail": "Password successfully reset."}, status=status.HTTP_200_OK
        )

    @extend_schema(description="Verify password reset code")
    @action(detail=False, methods=["post"])
    def password_reset_verify(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        user = User.objects.filter(email=email).first()
        reset_code = PasswordReset.objects.filter(user=user).first() if user else None
        if not reset_code:
            return Response(
                {"detail": "No reset request found for this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not reset_code.verify(code):
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Valid code."}, status=status.HTTP_200_OK)

    @extend_schema(description="Request e-mail change")
    @action(detail=False, methods=["post"])
    def email_change_request(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_email = serializer.validated_data["new_email"]
        user = request.user
        if User.objects.filter(email=new_email).exists():
            return Response(
                {"detail": "This e-mail is already in use."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_code = f"{secrets.randbelow(1000000):06d}"
        try:
            EmailChange.objects.filter(user=user).delete()
            change_code = EmailChange(user=user, new_email=new_email)
            change_code.set_code(raw_code)
            change_code.save()
            send_email_token(new_email, raw_code, "Confirm your new e-mail address")
        except Exception:
            transaction.set_rollback(True)
            return Response(
                {"detail": "Failed to send e-mail with code. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Code sent."}, status=status.HTTP_200_OK)

    @extend_schema(description="Confirm e-mail change")
    @action(detail=False, methods=["post"])
    def email_change_confirm(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        user = request.user
        change_code = EmailChange.objects.filter(user=user).first()
        if not change_code:
            return Response(
                {"detail": "No email change request found for this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not change_code.verify(code):
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.email = change_code.new_email
        user.save(update_fields=["email", "updated_at"])
        change_code.mark_used()
        return Response(
            {"detail": "E-mail successfully changed."}, status=status.HTTP_200_OK
        )

    @extend_schema(description="Verify e-mail change code")
    @action(detail=False, methods=["post"])
    def email_change_verify(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        user = request.user
        change_code = EmailChange.objects.filter(user=user).first()
        if not change_code:
            return Response(
                {"detail": "No email change request found for this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not change_code.verify(code):
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Valid code."}, status=status.HTTP_200_OK)

    @extend_schema(description="Login to the system", responses={200: None, 401: None})
    @action(detail=False, methods=["post"])
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
            {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
        )

    @extend_schema(description="Logout from the system", responses={200: None})
    @action(detail=False, methods=["post"])
    def logout(self, request):
        logout(request)
        return Response({"detail": "Successful logout."})
