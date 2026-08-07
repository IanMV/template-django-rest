from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as UserAdminFromDjango
from core.models import User

# Register your models here.


@admin.register(User)
class UserAdmin(UserAdminFromDjango):
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
                "classes": [
                    "collapse",
                ],
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
