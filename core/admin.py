from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as UserAdminFromDjango
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from core.auth.services import SessionService
from core.models.email_change import EmailChange
from core.models.email_verification import EmailVerification
from core.models.password_reset import PasswordReset
from core.models.user import User, UserSession


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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.is_active:
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


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "ip_address",
        "device_name",
        "is_active",
        "last_activity",
        "created_at",
    )
    search_fields = ("user__email", "user__name", "ip_address", "device_name")
    list_filter = ("is_active",)
    readonly_fields = (
        "id",
        "user",
        "access_jti",
        "refresh_jti",
        "device_name",
        "ip_address",
        "created_at",
        "last_activity",
        "is_active",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        SessionService.deactivate_session(obj.user, obj.pk)

    def delete_queryset(self, request, queryset):
        for session in queryset:
            SessionService.deactivate_session(session.user, session.pk)

