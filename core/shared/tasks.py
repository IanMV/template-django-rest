import logging
from smtplib import SMTPException

from celery import shared_task
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True)
def send_async_email(self, email: str, subject: str, text: str, html: str | None) -> None:
    message = EmailMultiAlternatives(subject=subject, body=text, to=[email])
    if html:
        message.attach_alternative(html, "text/html")
    try:
        if message.send() != 1:
            raise SMTPException("Email was not sent")
    except (SMTPException, OSError) as exc:
        if self.request.retries >= 3:
            logger.error("Email delivery failed after retries (%s)", type(exc).__name__)
        raise self.retry(
            exc=RuntimeError("Email delivery failed"),
            countdown=2 ** self.request.retries,
            max_retries=3,
        ) from None
    except Exception as exc:
        logger.error("Email task failed (%s)", type(exc).__name__)
        raise RuntimeError("Email delivery failed") from None
