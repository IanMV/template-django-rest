from unittest.mock import patch

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from core.admin import (
    CustomAdminAuthenticationForm,
    CustomAdminPasswordChangeForm,
    CustomUserCreationForm,
)
from core.auth.serializers import LoginSerializer
from core.email_change.serializers import (
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
)
from core.models import User
from core.password_reset.serializers import PasswordResetConfirmSerializer
from core.registration.serializers import RegistrationConfirmSerializer
from core.users.serializers import DeactivateSelfSerializer
from tests.base import ApiCase


class PasswordLengthTests(SimpleTestCase):
    def test_api_fields_enforce_limit_without_trimming(self):
        for serializer, name in (
            (LoginSerializer, "password"),
            (RegistrationConfirmSerializer, "password"),
            (PasswordResetConfirmSerializer, "new_password"),
            (EmailChangeRequestSerializer, "password"),
            (EmailChangeConfirmSerializer, "password"),
            (DeactivateSelfSerializer, "password"),
        ):
            field = serializer().fields[name]
            password = " " + "x" * 4094 + " "
            with self.subTest(serializer=serializer.__name__):
                self.assertEqual(field.run_validation(password), password)
                for oversized in (password + "x", "x" * 1_000_000):
                    with self.assertRaises(ValidationError):
                        field.run_validation(oversized)

    def test_admin_password_fields_enforce_same_limit(self):
        for form, names in (
            (CustomUserCreationForm(), ("password1", "password2")),
            (CustomAdminPasswordChangeForm(User()), ("password1", "password2")),
            (CustomAdminAuthenticationForm(), ("password",)),
        ):
            for name in names:
                field = form.fields[name]
                with self.subTest(form=type(form).__name__, field=name):
                    password = " " + "x" * 4094 + " "
                    self.assertEqual(field.clean(password), password)
                    with self.assertRaises(DjangoValidationError):
                        field.clean(password + "x")


class PasswordLengthBoundaryTests(ApiCase):
    def test_admin_login_rejects_large_input_before_authentication(self):
        from django.contrib import admin

        self.assertIs(admin.site.login_form, CustomAdminAuthenticationForm)
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            form = CustomAdminAuthenticationForm(
                data={
                    "username": "missing@example.com",
                    "password": "x" * 1_000_000,
                }
            )
            self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)
        authenticate.assert_not_called()

    def test_maximum_length_password_authenticates_without_truncation(self):
        password = " " + "x" * 4094 + " "
        user = self.create_user(password=password)
        self.login(user, password=password)

    def test_legacy_oversized_password_can_be_recovered(self):
        user = self.create_user(password="x" * 4097)
        self.assertEqual(
            self.client.post(
                "/api/login/",
                {
                    "email": user.email,
                    "password": "x" * 4097,
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/password-reset/request/",
                {
                    "email": user.email,
                },
            ).status_code,
            200,
        )
        response = self.client.post(
            "/api/password-reset/confirm/",
            {
                "email": user.email,
                "code": self.email_code(),
                "new_password": self.password,
            },
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.login(user)

    def test_login_rejects_large_input_before_authentication(self):
        with patch("core.auth.services.authenticate") as authenticate:
            response = self.client.post(
                "/api/login/",
                {"email": "missing@example.com", "password": "x" * 1_000_000},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        authenticate.assert_not_called()

    def test_registration_and_reset_reject_before_password_validation(self):
        for serializer, field, module in (
            (
                RegistrationConfirmSerializer,
                "password",
                "core.registration.serializers",
            ),
            (
                PasswordResetConfirmSerializer,
                "new_password",
                "core.password_reset.serializers",
            ),
        ):
            with self.subTest(serializer=serializer.__name__):
                with patch(f"{module}.validate_password") as validate:
                    instance = serializer(
                        data={
                            "email": "user@example.com",
                            "code": "123456",
                            "name": "Example Person",
                            field: "x" * 4097,
                        }
                    )
                    self.assertFalse(instance.is_valid())
                self.assertIn(field, instance.errors)
                validate.assert_not_called()
