import hashlib
import logging
import re

from django.core.cache import cache
from user_agents import parse

from core.models import AuditLog
from core.shared.client_ip import get_client_ip

logger = logging.getLogger(__name__)

# Only fixed event-specific values may enter details_json. Never store raw credentials or addresses.
DETAILS = {
    "LOGIN": {"email_hash"},
    "LOGOUT": set(),
    "REFRESH": set(),
    "REFRESH_REUSE": set(),
    "SESSION_ABSOLUTE_EXPIRED": set(),
    "SESSION_REVOKE": {"scope"},
    "PASSWORD_RESET": set(),
    "EMAIL_CHANGE": set(),
    "REAUTH": {"action"},
    "USER_LIST_ACCESS": set(),
}
ACTIONS = {"email_change_request", "email_change_confirm", "deactivate_self"}
SCOPES = {"all", "other", "current"}


def email_digest(email):
    return hashlib.sha256(email.strip().casefold().encode()).hexdigest()


def record_event(request, user, event, status, details=None):
    try:
        if event not in DETAILS or status not in AuditLog.Status.values:
            raise ValueError("Unsupported audit event")
        supplied = details if isinstance(details, dict) else {}
        filtered = {}
        for key in DETAILS[event]:
            value = supplied.get(key)
            if key == "email_hash" and isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
                filtered[key] = value
            elif key == "action" and isinstance(value, str) and value in ACTIONS:
                filtered[key] = value
            elif key == "scope" and isinstance(value, str) and value in SCOPES:
                filtered[key] = value

        ip = get_client_ip(request) if request else None
        session_id = supplied.get("session_id")
        if type(session_id) is not int or session_id <= 0:
            auth = getattr(request, "auth", None) if request else None
            session_id = auth.get("session_id") if hasattr(auth, "get") else None
        if type(session_id) is not int or session_id <= 0:
            session_id = None

        if status == AuditLog.Status.BLOCKED:
            subject = str(user.pk) if user else filtered.get("email_hash", "anonymous")
            digest = hashlib.sha256(f"{event}:{subject}:{ip}".encode()).hexdigest()
            if not cache.add(f"audit:blocked:{digest}", True, timeout=60):
                return None

        agent = parse(request.META.get("HTTP_USER_AGENT", "")) if request else None
        families = (
            [
                name if isinstance(name, str) and re.fullmatch(r"[A-Za-z .-]{1,80}", name) else "Other"
                for name in (agent.browser.family, agent.os.family)
            ]
            if agent
            else []
        )
        return AuditLog.objects.create(
            user=user,
            user_uuid_snapshot=user.pk if user else None,
            event_type=event,
            status=status,
            details_json=filtered,
            ip_address=ip,
            user_agent=" on ".join(families)[:512],
            session_id=session_id,
        )
    except Exception:
        logger.exception("Audit write failed")
        return None
