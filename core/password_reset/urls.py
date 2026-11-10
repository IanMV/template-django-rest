from django.urls import path

from core.password_reset.views import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
)

urlpatterns = [
    path("request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
