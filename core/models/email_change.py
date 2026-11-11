from django.db import models
from django.utils.translation import gettext_lazy as _

from .one_time_code import OneTimeCode
from .user import UserManager


class EmailChange(OneTimeCode):
    """One-time code for confirming a new email address."""

    new_email = models.EmailField(
        _("new email address"),
    )

    class Meta(OneTimeCode.Meta):
        abstract = False
        verbose_name = _("email change code")
        verbose_name_plural = _("email change codes")

    def clean(self):
        super().clean()
        self.new_email = UserManager.normalize_email(self.new_email)

    def save(self, *args, **kwargs):
        self.new_email = UserManager.normalize_email(self.new_email)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"EmailChange({self.user.email} -> {self.new_email})"
