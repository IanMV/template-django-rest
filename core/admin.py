from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as UserAdminFromDjango

from core.models import OneTimeCode, User


@admin.register(User)
class UserAdmin(UserAdminFromDjango):
    """User administration panel"""

    ordering = None

    list_display = (
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "email",
        "groups__name",
        "user_permissions__name",
        "user_permissions__codename",
    )

    fieldsets = (
        (
            "Authentication",
            {
                "fields": (
                    "email",
                    "password",
                    "id",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "created_at",
                )
            },
        ),
        (
            "Groups",
            {"fields": ("groups",)},
        ),
        (
            "User Permissions",
            {"fields": ("user_permissions",)},
        ),
    )

    readonly_fields = (
        "last_login",
        "id",
        "created_at",
    )

    add_fieldsets = (
        (
            "Required",
            {
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
        (
            "Optional",
            {
                "classes": ["collapse"],
                "fields": (
                    "groups",
                    "user_permissions",
                ),
            },
        ),
    )


@admin.register(OneTimeCode)
class OneTimeCodeAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "used", "used_at"]
    list_filter = ["used"]
    search_fields = ["user__email"]
    readonly_fields = ["code", "created_at", "used_at"]
