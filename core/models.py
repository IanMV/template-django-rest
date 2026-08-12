import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(
                "The email address is required.",
            )

        email = self.normalize_email(
            email,
        )

        user = self.model(
            email=email,
            **extra_fields,
        )

        user.set_password(
            password,
        )

        user.save(
            using=self._db,
        )
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault(
            "is_staff",
            True,
        )

        extra_fields.setdefault(
            "is_superuser",
            True,
        )

        return self.create_user(
            email,
            password,
            **extra_fields,
        )


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
    )

    email = models.EmailField(
        unique=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    is_staff = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS: list[str] = []

    objects: UserManager = UserManager()

    def __str__(self) -> str:
        return self.email
