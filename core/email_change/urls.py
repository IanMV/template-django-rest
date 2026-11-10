from django.urls import path

from core.email_change.views import (
    EmailChangeConfirmView,
    EmailChangeRequestView,
)

urlpatterns = [
    path("request/", EmailChangeRequestView.as_view(), name="email-change-request"),
    path("confirm/", EmailChangeConfirmView.as_view(), name="email-change-confirm"),
]
