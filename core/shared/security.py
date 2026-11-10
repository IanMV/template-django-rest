import logging

logger = logging.getLogger("core.security")

EVENTS = {
    "LOGIN",
    "LOGOUT",
    "PASSWORD_RESET",
    "EMAIL_CHANGE",
    "DEACTIVATE",
    "REAUTH",
}


def record_event(event, outcome):
    if event not in EVENTS or outcome not in {"SUCCESS", "FAILURE", "BLOCKED"}:
        raise ValueError("Unsupported security event")
    logger.info("Security event: %s %s", event, outcome)
