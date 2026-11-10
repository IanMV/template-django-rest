from django.urls import path

from core.registration.views import (
    RegistrationConfirmView,
    RegistrationRequestView,
)

urlpatterns = [
    path("request/", RegistrationRequestView.as_view(), name="registration-request"),
    path("confirm/", RegistrationConfirmView.as_view(), name="registration-confirm"),
]
