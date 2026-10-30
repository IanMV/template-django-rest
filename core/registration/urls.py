from django.urls import path

from core.registration.views import (
    RegistrationConfirmView,
    RegistrationRequestView,
    RegistrationVerifyView,
)

urlpatterns = [
    path("request/", RegistrationRequestView.as_view(), name="registration-request"),
    path("verify/", RegistrationVerifyView.as_view(), name="registration-verify"),
    path("confirm/", RegistrationConfirmView.as_view(), name="registration-confirm"),
]
