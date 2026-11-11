from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin as UserAdminFromDjango
from django.contrib.auth.forms import (
    AdminPasswordChangeForm,
    UserChangeForm,
    UserCreationForm,
)
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import connections, router, transaction
from django.utils.translation import gettext_lazy as _

from core.auth.services import SessionService
from core.models.email_change import EmailChange
from core.models.email_verification import EmailVerification
from core.models.password_reset import PasswordReset
from core.models.user import User
from core.shared.passwords import MAX_PASSWORD_LENGTH
from core.shared.response_messages import MSG_EMAIL_IN_USE


class CustomAdminAuthenticationForm(AdminAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["password"]
        field.validators.append(MaxLengthValidator(MAX_PASSWORD_LENGTH))
        field.widget.attrs["maxlength"] = MAX_PASSWORD_LENGTH


admin.site.login_form = CustomAdminAuthenticationForm


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("password1", "password2"):
            field = self.fields[name]
            field.validators.append(MaxLengthValidator(MAX_PASSWORD_LENGTH))
            field.widget.attrs["maxlength"] = MAX_PASSWORD_LENGTH

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"])

    def validate_unique(self):
        queryset = User.objects.filter(email=self.instance.email)
        if connections[router.db_for_write(User)].in_atomic_block:
            queryset = queryset.select_for_update(no_key=True)
        occupant = queryset.first()
        if occupant is None or not occupant.is_provisional_registration:
            return super().validate_unique()
        exclude = self._get_validation_exclusions()
        exclude.add("email")
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as exc:
            self._update_errors(exc)

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            with transaction.atomic(using=router.db_for_write(User)):
                if not User.objects.release_provisional_email(user.email):
                    raise ValidationError({"email": MSG_EMAIL_IN_USE})
                user.save()
                self.save_m2m()
        return user


class CustomUserChangeForm(UserChangeForm):
    security_state = forms.CharField(widget=forms.HiddenInput)

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    @staticmethod
    def state_for(user):
        return [str(user.pk), user.email, user.is_active, user.session_version]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["security_state"] = signing.dumps(
            self.state_for(self.instance), salt="core.admin.user-state"
        )

    def clean(self):
        cleaned = super().clean()
        token = cleaned.get("security_state")
        if token:
            try:
                state = signing.loads(token, salt="core.admin.user-state")
            except signing.BadSignature:
                raise ValidationError(
                    _("Invalid user state. Reload the form.")
                ) from None
            if state != self.state_for(self.instance):
                raise ValidationError(
                    _("The user's security state changed. Reload the form.")
                )
        return cleaned

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"])


class CustomAdminPasswordChangeForm(AdminPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("password1", "password2"):
            field = self.fields[name]
            field.validators.append(MaxLengthValidator(MAX_PASSWORD_LENGTH))
            field.widget.attrs["maxlength"] = MAX_PASSWORD_LENGTH

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            PasswordReset.objects.filter(user=user).delete()
            EmailChange.objects.filter(user=user).delete()
            EmailVerification.objects.filter(user=user).delete()
            if not user.has_usable_password():
                SessionService.revoke_all_sessions(user)
        return user


class NoAddModelAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(UserAdminFromDjango):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    change_password_form = CustomAdminPasswordChangeForm
    ordering = ("-created_at",)

    list_display = (
        "email",
        "name",
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
    )

    search_fields = (
        "name",
        "email",
        "groups__name",
        "user_permissions__name",
        "user_permissions__codename",
    )

    readonly_fields = (
        "id",
        "last_login",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Identification"),
            {
                "fields": (
                    "id",
                    "name",
                    "email",
                    "password",
                    "security_state",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        (
            _("Important dates"),
            {
                "fields": (
                    "last_login",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            _("Groups & Permissions"),
            {
                "classes": ("collapse",),
                "fields": (
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        alias = router.db_for_write(self.model)
        if (
            obj is not None
            and request.method == "POST"
            and connections[alias].in_atomic_block
        ):
            # Reload under lock before forms can retain stale authentication state.
            return (
                self.get_queryset(request)
                .using(alias)
                .select_for_update(no_key=True)
                .filter(pk=obj.pk)
                .first()
            )
        return obj

    def user_change_password(self, request, id, form_url=""):
        with transaction.atomic(using=router.db_for_write(self.model)):
            return super().user_change_password(request, id, form_url)

    def save_model(self, request, obj, form, change):
        if not change and not User.objects.release_provisional_email(obj.email):
            raise ValidationError({"email": MSG_EMAIL_IN_USE})
        super().save_model(request, obj, form, change)
        if change and {"email", "is_active"}.intersection(form.changed_data):
            PasswordReset.objects.filter(user=obj).delete()
            EmailChange.objects.filter(user=obj).delete()
            EmailVerification.objects.filter(user=obj).delete()
            SessionService.revoke_all_sessions(obj)


class OneTimeCodeAdmin(NoAddModelAdmin):
    list_display = (
        "user",
        "attempts",
        "used",
        "created_at",
        "expires_at",
    )

    readonly_fields = (
        "id",
        "user",
        "used",
        "used_at",
        "attempts",
        "created_at",
        "expires_at",
    )

    fieldsets = (
        (
            _("User Info"),
            {
                "fields": (
                    "id",
                    "user",
                )
            },
        ),
        (
            _("Usage Status"),
            {
                "fields": (
                    "used",
                    "used_at",
                    "attempts",
                )
            },
        ),
        (
            _("Validity Dates"),
            {
                "fields": (
                    "created_at",
                    "expires_at",
                )
            },
        ),
    )

    search_fields = (
        "user__email",
        "user__name",
    )


@admin.register(EmailVerification)
class EmailVerificationAdmin(OneTimeCodeAdmin):
    pass


@admin.register(PasswordReset)
class PasswordResetAdmin(OneTimeCodeAdmin):
    pass


@admin.register(EmailChange)
class EmailChangeAdmin(OneTimeCodeAdmin):
    list_display = (
        "user",
        "new_email",
        "attempts",
        "used",
        "created_at",
    )

    readonly_fields = OneTimeCodeAdmin.readonly_fields + ("new_email",)

    fieldsets = (
        (
            _("User Info"),
            {
                "fields": (
                    "id",
                    "user",
                    "new_email",
                )
            },
        ),
        (
            _("Usage Status"),
            {
                "fields": (
                    "used",
                    "used_at",
                    "attempts",
                )
            },
        ),
        (
            _("Validity Dates"),
            {
                "fields": (
                    "created_at",
                    "expires_at",
                )
            },
        ),
    )

    search_fields = OneTimeCodeAdmin.search_fields + ("new_email",)
