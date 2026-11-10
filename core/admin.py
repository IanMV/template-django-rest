from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as UserAdminFromDjango
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.db import router, transaction
from django.utils.translation import gettext_lazy as _

from core.auth.services import SessionService
from core.models.email_change import EmailChange
from core.models.email_verification import EmailVerification
from core.models.password_reset import PasswordReset
from core.models.user import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "name")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class NoAddModelAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False


@admin.register(User)
class UserAdmin(UserAdminFromDjango):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
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
        if obj is not None and request.method == "POST":
            # Reload under lock before forms can retain stale authentication state.
            return (
                self.get_queryset(request)
                .select_for_update(no_key=True)
                .filter(pk=obj.pk)
                .first()
            )
        return obj

    def user_change_password(self, request, id, form_url=""):
        with transaction.atomic(using=router.db_for_write(self.model)):
            return super().user_change_password(request, id, form_url)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and "email" in form.changed_data:
            PasswordReset.objects.filter(user=obj).delete()
            EmailChange.objects.filter(user=obj).delete()
            EmailVerification.objects.filter(user=obj).delete()
        if change and {"email", "is_active"}.intersection(form.changed_data):
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
