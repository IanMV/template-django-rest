import uuid

from asgiref.sync import sync_to_async
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        email = email.strip().lower() if email else ""
        local, separator, domain = email.rpartition("@")
        if separator:
            try:
                email = f"{local}@{domain.encode('idna').decode('ascii')}"
            except UnicodeError:
                raise ValidationError(
                    _("Enter a valid email address."), code="invalid"
                ) from None
        if len(email) > 254:
            raise ValidationError(
                _("Ensure this value has at most 254 characters."), code="max_length"
            )
        return email

    def get_by_natural_key(self, username):
        try:
            email = self.normalize_email(username)
        except ValidationError:
            raise self.model.DoesNotExist from None
        return self.get(email=email)

    def release_provisional_email(self, email):
        # The caller must keep this lock until the replacement is saved.
        occupant = self.select_for_update(no_key=True).filter(email=email).first()
        if occupant is None:
            return True
        if not occupant.is_provisional_registration:
            return False
        occupant.delete()
        return True

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
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="core_user_created_id_idx")
        ]
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

    def check_password(self, raw_password):
        encoded = self.password
        upgraded = True

        def setter(raw_password):
            nonlocal upgraded
            password = make_password(raw_password)
            # A hash upgrade must never overwrite a concurrent password change.
            upgraded = bool(
                type(self)
                .objects.using(self._state.db)
                .filter(pk=self.pk, password=encoded)
                .update(password=password)
            )
            if upgraded:
                self.password = password
                self._password = None

        return check_password(raw_password, encoded, setter) and upgraded

    async def acheck_password(self, raw_password):
        return await sync_to_async(self.check_password)(raw_password)

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>" if self.name else self.email

    def get_full_name(self) -> str:
        return self.name.strip()

    def get_short_name(self) -> str:
        parts = self.name.split()
        return parts[0] if parts else self.email

    @property
    def is_provisional_registration(self):
        return (
            not self.is_active
            and self.password == ""
            and not self.is_staff
            and not self.is_superuser
            and not self.name
            and self.last_login is None
            and self.session_version == 0
            and not self.groups.exists()
            and not self.user_permissions.exists()
            and not self.logentry_set.exists()
            and not hasattr(self, "passwordreset")
            and not hasattr(self, "emailchange")
        )

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
