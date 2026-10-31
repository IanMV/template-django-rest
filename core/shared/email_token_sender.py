from django.utils import timezone

from core.shared.email_templates import render_email_token
from core.shared.tasks import send_async_email


def queue_email(
    email: str, subject: str, text: str, html: str | None = None, *, expires=900
) -> None:
    send_async_email.apply_async(
        args=(email, subject, text, html),
        expires=expires,
        argsrepr="(<redacted>)",
        kwargsrepr="{<redacted>}",
    )


def send_email_token(
    email: str, code: str, template_name: str, *, expires_at=None
) -> None:
    subject, text, html = render_email_token(template_name, code)
    if expires_at is not None and expires_at <= timezone.now():
        raise ValueError("Email code has expired")
    queue_email(email, subject, text, html, expires=expires_at or 900)
