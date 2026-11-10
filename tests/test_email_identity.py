from django.db import IntegrityError, transaction

from core.admin import CustomUserChangeForm, CustomUserCreationForm
from core.models import User
from tests.base import ApiCase


class EmailIdentityTests(ApiCase):
    def test_manager_and_admin_normalize_email(self):
        user = self.create_user(email="Manager@EXAMPLE.COM")
        self.assertEqual(user.email, "manager@example.com")
        self.assertEqual(
            User.objects.get_by_natural_key("MANAGER@EXAMPLE.COM").pk, user.pk
        )
        form = CustomUserCreationForm(
            {
                "email": "Admin@EXAMPLE.COM",
                "name": "Staff Added",
                "password1": "StaffPass!7483",
                "password2": "StaffPass!7483",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        admin = form.save()
        self.assertEqual(admin.email, "admin@example.com")
        changed = CustomUserChangeForm(
            {
                "email": "Changed@EXAMPLE.COM",
                "name": admin.name,
                "password": admin.password,
                "is_active": True,
            },
            instance=admin,
        )
        self.assertTrue(changed.is_valid(), changed.errors)
        self.assertEqual(changed.save().email, "changed@example.com")
        duplicate = CustomUserCreationForm(
            {
                "email": "MANAGER@EXAMPLE.COM",
                "name": "Duplicate",
                "password1": "StaffPass!7483",
                "password2": "StaffPass!7483",
            }
        )
        self.assertFalse(duplicate.is_valid())
        self.assertIn("email", duplicate.errors)

    def test_database_rejects_noncanonical_and_duplicate_email(self):
        user = self.create_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(email="PERSON@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="BYPASS@example.com", name="Bypass")])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_user(email="PERSON@EXAMPLE.COM")

    def test_case_variants_work_across_account_flows(self):
        response = self.client.post(
            "/api/registration/request/", {"email": "Person@EXAMPLE.COM"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/registration/confirm/",
            {
                "email": "PERSON@example.com",
                "code": self.email_code(),
                "name": "Example Person",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="person@example.com")
        user.email = "PERSON@EXAMPLE.COM"
        self.login(user)
        response = self.client.post(
            "/api/email-change/request/",
            {
                "new_email": "New@EXAMPLE.COM",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/email-change/confirm/",
            {
                "code": self.email_code(),
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/password-reset/request/", {"email": "NEW@EXAMPLE.COM"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/password-reset/confirm/",
            {
                "email": "New@example.com",
                "code": self.email_code(),
                "new_password": "ChangedPass!7395",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password("ChangedPass!7395"))
