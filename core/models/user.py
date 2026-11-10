import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        return email.strip().lower() if email else ""

    def get_by_natural_key(self, username):
        return self.get(email=self.normalize_email(username))

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("The given email address must be set."))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not password:
            raise ValueError(_("Superuser must have a password."))
        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    session_version = models.PositiveBigIntegerField(default=0, editable=False)

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        _("name"),
        max_length=255,
        blank=False,
    )

    email = models.EmailField(
        _("email address"),
        unique=True,
        blank=False,
    )

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )

    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(email=Lower(Trim("email"))),
                name="core_user_email_canonical",
            )
        ]

    def clean(self):
        super().clean()
        self.email = UserManager.normalize_email(self.email)

    def save(self, *args, **kwargs):
        self.email = UserManager.normalize_email(self.email)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>" if self.name else self.email

    def get_full_name(self) -> str:
        return self.name.strip()

    def get_short_name(self) -> str:
        return self.name.split()[0] if self.name else self.email

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def _get_session_auth_hash(self, secret=None):
        # Include account state so reactivation cannot restore revoked sessions.
        return salted_hmac(
            "core.User.session",
            f"{self.password}:{self.email}:{self.is_active}:{self.session_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()
