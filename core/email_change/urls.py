from django.urls import path

from core.email_change.views import (
    EmailChangeConfirmView,
    EmailChangeRequestView,
    EmailChangeVerifyView,
)

urlpatterns = [
    path("request/", EmailChangeRequestView.as_view(), name="email-change-request"),
    path("verify/", EmailChangeVerifyView.as_view(), name="email-change-verify"),
    path("confirm/", EmailChangeConfirmView.as_view(), name="email-change-confirm"),
]
