from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from core.shared.email_templates import render_email_token


def send_email(email, subject, text, html=None):
    message = EmailMultiAlternatives(subject=subject, body=text, to=[email])
    if html:
        message.attach_alternative(html, "text/html")
    if message.send() != 1:
        raise RuntimeError("Email was not sent")


def send_email_token(email, code, template_name, *, expires_at):
    if expires_at <= timezone.now():
        raise ValueError("Email code has expired")
    subject, text, html = render_email_token(template_name, code)
    send_email(email, subject, text, html)
