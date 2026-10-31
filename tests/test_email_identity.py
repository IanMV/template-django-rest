from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.admin import CustomUserChangeForm, CustomUserCreationForm
from core.models import User
from tests.base import ApiCase, ApiTransactionCase


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
        user = self.create_user(email="person@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(email="PERSON@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="BYPASS@example.com", name="Bypass")])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_user(email="PERSON@EXAMPLE.COM")

    def test_case_variants_work_across_account_flows(self):
        issued = self.post_with_commit(
            "/api/registration/request/", {"email": "Person@EXAMPLE.COM"}
        )
        self.assertEqual(issued.status_code, 201)
        code = self.email_code()
        verified = self.client.post(
            "/api/registration/verify/",
            {"email": "PERSON@example.com", "code": code},
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        confirmed = self.client.post(
            "/api/registration/confirm/",
            {
                "email": "person@Example.COM",
                "code": code,
                "name": "Example Person",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)
        user = User.objects.get(email="person@example.com")
        user.email = "PERSON@EXAMPLE.COM"
        self.login(user)
        user.refresh_from_db()
        duplicate = self.client.post(
            "/api/email-change/request/",
            {"new_email": "PERSON@EXAMPLE.COM", "password": self.password},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        changed = self.post_with_commit(
            "/api/email-change/request/",
            {"new_email": "New@EXAMPLE.COM", "password": self.password},
            REMOTE_ADDR="127.0.0.2",
        )
        self.assertEqual(changed.status_code, 200)
        change_code = self.email_code()
        verified = self.client.post(
            "/api/email-change/verify/", {"code": change_code}, format="json"
        )
        self.assertEqual(verified.status_code, 200)
        confirmed = self.client.post(
            "/api/email-change/confirm/",
            {"code": change_code, "password": self.password},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        reset = self.post_with_commit(
            "/api/password-reset/request/", {"email": "NEW@EXAMPLE.COM"}
        )
        self.assertEqual(reset.status_code, 200)
        reset_code = self.email_code()
        verified = self.client.post(
            "/api/password-reset/verify/",
            {"email": "New@example.com", "code": reset_code},
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        confirmed = self.client.post(
            "/api/password-reset/confirm/",
            {
                "email": "new@Example.COM",
                "code": reset_code,
                "new_password": "ChangedPass!7395",
            },
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("ChangedPass!7395"))


class EmailIdentityMigrationTests(ApiTransactionCase):
    def test_existing_emails_are_normalized_without_account_changes(self):
        old = ("core", "0004_auditlog")
        latest = ("core", "0005_normalize_user_email")
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        apps = executor.loader.project_state([old]).apps
        legacy_user = apps.get_model("core", "User")
        user = legacy_user.objects.create(
            email=" Legacy@EXAMPLE.COM ",
            name="Legacy",
            password="unchanged",
            is_staff=True,
        )
        change = apps.get_model("core", "EmailChange").objects.create(
            user=user, new_email=" New@EXAMPLE.COM ", code="unchanged"
        )
        try:
            MigrationExecutor(connection).migrate([latest])
            current = User.objects.get(pk=user.pk)
            self.assertEqual(current.email, "legacy@example.com")
            self.assertTrue(current.is_staff)
            self.assertEqual(current.password, "unchanged")
            change.refresh_from_db()
            self.assertEqual(change.new_email, "new@example.com")
        finally:
            legacy_user.objects.filter(pk=user.pk).delete()
            MigrationExecutor(connection).migrate([latest])

    def test_collision_aborts_before_rewriting_or_merging_accounts(self):
        old = ("core", "0004_auditlog")
        latest = ("core", "0005_normalize_user_email")
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        legacy_user = executor.loader.project_state([old]).apps.get_model(
            "core", "User"
        )
        first = legacy_user.objects.create(email="Person@EXAMPLE.COM", name="First")
        second = legacy_user.objects.create(email="person@example.com", name="Second")
        try:
            with self.assertRaisesMessage(
                RuntimeError, "Email identity collisions exist"
            ):
                MigrationExecutor(connection).migrate([latest])
            first.refresh_from_db()
            second.refresh_from_db()
            self.assertEqual(first.email, "Person@EXAMPLE.COM")
            self.assertEqual(second.email, "person@example.com")
            self.assertEqual(
                legacy_user.objects.filter(pk__in=[first.pk, second.pk]).count(), 2
            )
        finally:
            legacy_user.objects.filter(pk__in=[first.pk, second.pk]).delete()
            MigrationExecutor(connection).migrate([latest])
