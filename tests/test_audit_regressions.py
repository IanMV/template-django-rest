from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from core.admin import CustomUserCreationForm
from core.auth.serializers import LoginSerializer
from core.email_change.serializers import EmailChangeRequestSerializer
from core.models import EmailChange, EmailVerification, PasswordReset, User
from core.password_reset.serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from core.registration.serializers import (
    RegistrationConfirmSerializer,
    RegistrationRequestSerializer,
)
from tests.base import ApiCase


class EmailLengthTests(SimpleTestCase):
    def test_email_fields_match_storage_limit(self):
        for serializer_class, field_name in (
            (LoginSerializer, "email"),
            (RegistrationRequestSerializer, "email"),
            (RegistrationConfirmSerializer, "email"),
            (PasswordResetRequestSerializer, "email"),
            (PasswordResetConfirmSerializer, "email"),
            (EmailChangeRequestSerializer, "new_email"),
        ):
            field = serializer_class().fields[field_name]
            for length in (254, 255, 259, 320):
                email = "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "."
                email += "d" * (length - len(email) - 4) + ".com"
                with self.subTest(serializer=serializer_class.__name__, length=length):
                    if length == 254:
                        self.assertEqual(field.run_validation(email), email)
                    else:
                        with self.assertRaises(ValidationError):
                            field.run_validation(email)


class ProvisionalEmailTests(ApiCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_user()
        self.login(self.owner)

    def reserve(self):
        public = self.new_client()
        self.bootstrap(public)
        response = public.post(
            "/api/registration/request/", {"email": "target@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        return User.objects.get(email="target@example.com")

    def request_change(self):
        return self.client.post(
            "/api/email-change/request/",
            {"new_email": "target@example.com", "password": self.password},
            format="json",
        )

    def confirm(self, code):
        return self.client.post(
            "/api/email-change/confirm/",
            {"code": code, "password": self.password},
            format="json",
        )

    def test_reservation_before_request_does_not_block_verified_change(self):
        pending = self.reserve()
        self.assertEqual(self.request_change().status_code, 200)
        self.assertTrue(User.objects.filter(pk=pending.pk).exists())
        self.assertEqual(self.confirm(self.email_code()).status_code, 200)
        self.assertFalse(User.objects.filter(pk=pending.pk).exists())
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "target@example.com")

    def test_reservation_after_request_does_not_block_verified_change(self):
        self.assertEqual(self.request_change().status_code, 200)
        code = self.email_code()
        self.reserve()
        self.assertEqual(self.confirm(code).status_code, 200)

    def test_invalid_code_and_admin_form_leave_reservation_intact(self):
        self.assertEqual(self.request_change().status_code, 200)
        pending = self.reserve()
        self.assertEqual(self.confirm("invalid").status_code, 400)
        form = CustomUserCreationForm(data={"email": pending.email, "name": "Admin"})
        self.assertFalse(form.is_valid())
        self.assertTrue(User.objects.filter(pk=pending.pk).exists())

    def test_admin_can_replace_only_an_empty_registration(self):
        pending = self.reserve()
        form = CustomUserCreationForm(
            data={
                "email": pending.email,
                "name": "Admin created",
                "password1": "StaffPass!7483",
                "password2": "StaffPass!7483",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.is_active)
        self.assertFalse(User.objects.filter(pk=pending.pk).exists())
        self.assertTrue(user.check_password("StaffPass!7483"))

    def test_activated_reservation_is_never_replaced(self):
        self.assertEqual(self.request_change().status_code, 200)
        code = self.email_code()
        pending = self.reserve()
        pending.is_active = True
        pending.set_password(self.password)
        pending.save()
        self.assertEqual(self.confirm(code).status_code, 400)
        self.assertTrue(User.objects.filter(pk=pending.pk, is_active=True).exists())

    def test_related_permissions_prevent_replacement(self):
        from django.contrib.auth.models import Group

        pending = self.reserve()
        pending.groups.add(Group.objects.create(name="Protected"))
        self.assertEqual(self.request_change().status_code, 200)
        self.assertFalse(EmailChange.objects.filter(user=self.owner).exists())
        self.assertTrue(User.objects.filter(pk=pending.pk).exists())

    def test_claim_rolls_back_if_session_revocation_fails(self):
        self.assertEqual(self.request_change().status_code, 200)
        code = self.email_code()
        pending = self.reserve()
        with patch(
            "core.email_change.services.SessionService.revoke_all_sessions",
            side_effect=RuntimeError("synthetic failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.confirm(code)
        self.assertTrue(User.objects.filter(pk=pending.pk).exists())
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "person@example.com")


class UniformEmailChangeTests(ApiCase):
    def test_occupied_and_free_addresses_have_uniform_responses_even_on_smtp_failure(
        self,
    ):
        self.login(self.create_user())
        self.create_user(email="occupied@example.com")
        with patch(
            "core.email_change.services.send_email_token", side_effect=OSError("SMTP")
        ):
            responses = []
            for email in ("occupied@example.com", "free@example.com"):
                cache.clear()
                responses.append(
                    self.client.post(
                        "/api/email-change/request/",
                        {"new_email": email, "password": self.password},
                        format="json",
                    )
                )
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(responses[0].data, responses[1].data)
        self.assertFalse(EmailChange.objects.exists())


class IssuanceDeduplicationTests(ApiCase):
    def test_database_cooldown_preserves_code_across_independent_caches(self):
        user = self.create_user()
        self.login(user)
        for flow, model, payload in (
            ("registration", EmailVerification, {"email": "pending@example.com"}),
            ("password-reset", PasswordReset, {"email": user.email}),
            (
                "email-change",
                EmailChange,
                {
                    "new_email": "new@example.com",
                    "password": self.password,
                },
            ),
        ):
            with self.subTest(flow=flow):
                cache.clear()
                path = f"/api/{flow}/request/"
                expected = 201 if flow == "registration" else 200
                self.assertEqual(self.client.post(path, payload).status_code, expected)
                first = model.objects.get()
                first.attempts = 2
                first.save(update_fields=["attempts"])
                sent = len(mail.outbox)
                cache.clear()
                self.assertEqual(self.client.post(path, payload).status_code, expected)
                current = model.objects.get()
                self.assertEqual(current.pk, first.pk)
                self.assertEqual(current.code, first.code)
                self.assertEqual(current.expires_at, first.expires_at)
                self.assertEqual(current.attempts, 2)
                self.assertEqual(len(mail.outbox), sent)
                cache.clear()
                with patch(
                    "django.utils.timezone.now",
                    return_value=first.created_at + timedelta(seconds=60),
                ):
                    self.assertEqual(
                        self.client.post(path, payload).status_code, expected
                    )
                self.assertNotEqual(model.objects.get().pk, first.pk)
                self.assertEqual(len(mail.outbox), sent + 1)


class CanonicalDomainTests(ApiCase):
    def test_idn_and_punycode_share_identity_and_limits(self):
        from core.auth.rate_limit import login_pair_key

        user = self.create_user(email="person@münchen.de")
        self.assertEqual(user.email, "person@xn--mnchen-3ya.de")
        self.assertEqual(
            User.objects.get_by_natural_key("PERSON@MÜNCHEN.DE").pk, user.pk
        )
        self.assertEqual(
            login_pair_key("person@münchen.de", "ip"), login_pair_key(user.email, "ip")
        )
        form = CustomUserCreationForm(
            data={
                "email": "person@münchen.de",
                "name": "Duplicate",
                "password1": "StaffPass!7483",
                "password2": "StaffPass!7483",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_canonicalization_is_idempotent_and_matches_smtp(self):
        from django.core.mail.backends.smtp import EmailBackend

        backend = EmailBackend(alias="default", host="localhost")
        for email in (
            "user@münchen.de",
            "USER@İSTANBUL.COM",
            "user@straße.de",
            "USER@EXAMPLE.COM",
        ):
            canonical = User.objects.normalize_email(email)
            self.assertEqual(User.objects.normalize_email(canonical), canonical)
            self.assertEqual(backend.prep_address(email.lower()), canonical)
        self.assertNotEqual(
            User.objects.normalize_email("user@İSTANBUL.COM"), "user@istanbul.com"
        )

    def test_expansion_and_invalid_domains_are_validation_errors(self):
        from django.core.exceptions import ValidationError as DjangoValidationError

        field = RegistrationRequestSerializer().fields["email"]
        domain = ".".join(["é" * 57] * 3)
        value = "a" * 64 + "@" + domain
        self.assertLess(len(value), 254)
        with self.assertRaises(ValidationError):
            field.run_validation(value)
        with self.assertRaises(DjangoValidationError):
            User.objects.normalize_email("user@" + "é" * 64 + ".com")
        with self.assertRaises(User.DoesNotExist):
            User.objects.get_by_natural_key("user@" + "é" * 64 + ".com")

    def test_existing_data_migration_detects_collisions_before_writing(self):
        migration = import_module("core.migrations.0002_canonical_email_domains")
        first = self.create_user(email="first@example.com")
        User.objects.filter(pk=first.pk).update(email="user@münchen.de")
        self.create_user(email="user@xn--mnchen-3ya.de")
        with self.assertRaisesMessage(RuntimeError, "collisions"):
            migration.canonicalize_domains(apps, SimpleNamespace(connection=connection))
        first.refresh_from_db()
        self.assertEqual(first.email, "user@münchen.de")

    def test_existing_data_migration_preserves_accounts_and_pending_codes(self):
        migration = import_module("core.migrations.0002_canonical_email_domains")
        user = self.create_user()
        User.objects.filter(pk=user.pk).update(email="user@münchen.de")
        change = EmailChange(user=user, new_email="new@example.com")
        change.set_code("123456")
        change.save()
        EmailChange.objects.filter(pk=change.pk).update(new_email="new@münchen.de")
        migration.canonicalize_domains(apps, SimpleNamespace(connection=connection))
        user.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(user.email, "user@xn--mnchen-3ya.de")
        self.assertEqual(change.new_email, "new@xn--mnchen-3ya.de")
        self.assertTrue(user.check_password(self.password))
        self.assertTrue(change.check_code("123456"))
        self.assertEqual(user.session_version, 0)
        self.assertFalse(change.used)

    def test_idn_registration_confirmation_and_login_use_one_identity(self):
        response = self.client.post(
            "/api/registration/request/", {"email": "user@münchen.de"}
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/registration/confirm/",
            {
                "email": "user@xn--mnchen-3ya.de",
                "code": self.email_code(),
                "name": "Example Person",
                "password": self.password,
            },
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="user@xn--mnchen-3ya.de")
        user.email = "USER@MÜNCHEN.DE"
        self.login(user)
        self.assertEqual(User.objects.count(), 1)


class AdminStateTests(ApiCase):
    def setUp(self):
        super().setUp()
        self.owner = self.create_user()
        self.login(
            self.create_user(
                email="admin@example.com", is_staff=True, is_superuser=True
            )
        )
        self.path = f"/admin/core/user/{self.owner.pk}/change/"

    def token(self):
        return (
            self.client.get(self.path)
            .context["adminform"]
            .form["security_state"]
            .value()
        )

    def submit(self, token):
        return self.client.post(
            self.path,
            {
                "email": self.owner.email,
                "is_active": "on",
                "name": "Edited",
                "security_state": token,
            },
        )

    def test_stale_form_does_not_reactivate_user_or_partially_save(self):
        from core.users.services import UserService

        token = self.token()
        UserService.deactivate_user(self.owner, self.password)
        response = self.submit(token)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "security state changed", str(response.context["adminform"].form.errors)
        )
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertEqual(self.owner.name, "Example Person")
        self.assertEqual(self.submit(self.token()).status_code, 302)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_stale_form_does_not_restore_previous_email(self):
        from core.email_change.services import EmailChangeService

        token = self.token()
        code = EmailChange(user=self.owner, new_email="changed@example.com")
        code.set_code("123456")
        code.save()
        EmailChangeService.confirm_change(self.owner, "123456", self.password)
        self.assertEqual(self.submit(token).status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "changed@example.com")
        self.assertEqual(self.owner.name, "Example Person")

    def test_missing_forged_and_other_user_tokens_are_rejected(self):
        from core.admin import CustomUserChangeForm

        for token in (
            "",
            self.token() + "tampered",
            CustomUserChangeForm(instance=self.create_user(email="other@example.com"))[
                "security_state"
            ].value(),
        ):
            with self.subTest(token_kind=bool(token)):
                self.assertEqual(self.submit(token).status_code, 200)
                self.owner.refresh_from_db()
                self.assertEqual(self.owner.name, "Example Person")

    def test_fresh_form_can_edit_name(self):
        self.assertEqual(self.submit(self.token()).status_code, 302)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.name, "Edited")


class DeterministicUserOrderTests(ApiCase):
    def test_tied_timestamps_have_a_unique_descending_tiebreaker(self):
        from uuid import UUID

        from django.utils import timezone

        from core.users.services import UserService

        for value in (3, 1, 2):
            self.create_user(email=f"tie-{value}@example.com", id=UUID(int=value))
        User.objects.update(created_at=timezone.now())
        self.assertEqual(
            list(UserService.list_users().values_list("pk", flat=True)),
            [UUID(int=value) for value in (3, 2, 1)],
        )

    def test_static_pages_do_not_repeat_or_omit_tied_users(self):
        from django.utils import timezone

        staff = self.create_user(is_staff=True)
        for number in range(3):
            self.create_user(email=f"page-{number}@example.com")
        User.objects.update(created_at=timezone.now())
        self.login(staff)
        ids = []
        for page in range(1, 5):
            response = self.client.get(f"/api/users/list/?page_size=1&page={page}")
            self.assertEqual(response.status_code, 200)
            ids.extend(item["id"] for item in response.data["results"])
        expected = sorted(
            (str(pk) for pk in User.objects.values_list("pk", flat=True)), reverse=True
        )
        self.assertEqual(ids, expected)


class ShortNameTests(SimpleTestCase):
    def test_whitespace_only_names_fall_back_without_changing_normal_names(self):
        for name, expected in (
            ("", "user@example.com"),
            (" \t\n ", "user@example.com"),
            (" First Last ", "First"),
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    User(name=name, email="user@example.com").get_short_name(), expected
                )
