from django.urls import path

from core.password_reset.views import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
)

urlpatterns = [
    path("request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("verify/", PasswordResetVerifyView.as_view(), name="password-reset-verify"),
    path("confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
