import logging
import time

from django.conf import settings
from django.core.cache import caches
from django.db import transaction

from core.models.user import UserSession

logger = logging.getLogger(__name__)


def session_is_active(token, *, use_cache=True):
    session_id = token.get("session_id")
    if session_id is not None and (type(session_id) is not int or session_id <= 0):
        return False
    jti = str(token.get("jti", ""))
    user_id = str(token.get("user_id", ""))
    if session_id is not None and use_cache:
        try:
            if caches["sessions"].get(f"session:{session_id}") == (jti, user_id):
                return True
        except Exception:
            logger.exception("Session cache lookup failed; checking database")

    sessions = UserSession.objects.filter(access_jti=jti, is_active=True)
    if session_id is not None:
        sessions = sessions.filter(pk=session_id, user_id=user_id)
    session = sessions.first()
    if not session:
        return False
    if session_id is not None and use_cache:
        timeout = min(
            settings.SESSION_CACHE_TTL,
            int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            int(token["exp"] - time.time()),
        )
        if timeout > 0:
            try:
                caches["sessions"].set(
                    f"session:{session.pk}", (jti, user_id), timeout=timeout
                )
            except Exception:
                logger.exception("Session cache write failed; using database result")
    if session_id is None:
        token["session_id"] = session.pk
    return True


def invalidate_sessions(session_ids):
    keys = [f"session:{session_id}" for session_id in session_ids]
    if not keys:
        return

    def delete():
        try:
            caches["sessions"].delete_many(keys)
        except Exception:
            # shortcut: failed deletes leave positive entries for at most SESSION_CACHE_TTL; use versioned sessions for strict revocation.
            logger.exception("Session cache invalidation failed")

    transaction.on_commit(delete)
