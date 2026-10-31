from core.admin import CustomUserCreationForm
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


class PasswordWhitespaceTests(ApiCase):
    def test_admin_password_authenticates_only_with_exact_spaces(self):
        password = "  StaffPass!7483  "
        form = CustomUserCreationForm(
            {
                "email": "admin@example.com",
                "name": "Staff Added",
                "password1": password,
                "password2": password,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.login(user, password=password)
        for wrong in (password.strip(), password.lstrip(), password.rstrip()):
            rejected = self.client.post(
                "/api/login/", {"email": user.email, "password": wrong}, format="json"
            )
            self.assertEqual(rejected.status_code, 401)

    def test_registration_reset_and_reauthentication_preserve_spaces(self):
        email, password = "person@example.com", "  StrongPass!4693$  "
        issued = self.post_with_commit("/api/registration/request/", {"email": email})
        self.assertEqual(issued.status_code, 201)
        confirmed = self.client.post(
            "/api/registration/confirm/",
            {
                "email": email,
                "code": self.email_code(),
                "name": "Example Person",
                "password": password,
            },
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)
        user = User.objects.get(email=email)
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.check_password(password.strip()))
        self.login(user, password=password)
        issued = self.post_with_commit("/api/password-reset/request/", {"email": email})
        self.assertEqual(issued.status_code, 200)
        password = "  DifferentPass!7395  "
        reset = self.client.post(
            "/api/password-reset/confirm/",
            {
                "email": email,
                "code": self.email_code(),
                "new_password": password,
            },
            format="json",
        )
        self.assertEqual(reset.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.check_password(password.strip()))
        self.login(user, password=password)
        rejected = self.client.post(
            "/api/email-change/request/",
            {"new_email": "new@example.com", "password": password.strip()},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        issued = self.post_with_commit(
            "/api/email-change/request/",
            {"new_email": "new@example.com", "password": password},
        )
        self.assertEqual(issued.status_code, 200)
        code = self.email_code()
        for supplied, status in ((password.strip(), 400), (password, 200)):
            changed = self.client.post(
                "/api/email-change/confirm/",
                {"code": code, "password": supplied},
                format="json",
            )
            self.assertEqual(changed.status_code, status)
        user.refresh_from_db()
        self.login(user, password=password)
        for supplied, status in ((password.strip(), 400), (password, 200)):
            deactivated = self.client.post(
                "/api/me/deactivate/", {"password": supplied}, format="json"
            )
            self.assertEqual(deactivated.status_code, status)

    def test_blank_and_weak_password_validation_is_preserved(self):
        payload = {
            "email": "person@example.com",
            "new_email": "new@example.com",
            "code": "123456",
            "name": "Example Person",
        }
        serializers = (
            (LoginSerializer, "password"),
            (RegistrationConfirmSerializer, "password"),
            (PasswordResetConfirmSerializer, "new_password"),
            (EmailChangeRequestSerializer, "password"),
            (EmailChangeConfirmSerializer, "password"),
            (DeactivateSelfSerializer, "password"),
        )
        for serializer_class, field in serializers:
            for password in ("", "         "):
                with self.subTest(
                    serializer=serializer_class.__name__, password=password
                ):
                    serializer = serializer_class(data={**payload, field: password})
                    self.assertFalse(serializer.is_valid())
                    self.assertIn(field, serializer.errors)
        for serializer_class, field in serializers[1:3]:
            serializer = serializer_class(data={**payload, field: "short"})
            self.assertFalse(serializer.is_valid())
