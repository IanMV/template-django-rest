from django.db import transaction

from core.auth.rate_limit import require_current_password
from core.auth.services import SessionService, require_unchanged_user
from core.models.user import User


class UserService:
    @staticmethod
    def list_users():
        return User.objects.filter(is_active=True).order_by("-created_at")

    @staticmethod
    def deactivate_user(requesting_user: User, current_password: str):
        require_current_password(requesting_user, current_password)
        with transaction.atomic():
            current = User.objects.select_for_update(no_key=True).filter(pk=requesting_user.pk).first()
            require_unchanged_user(requesting_user, current)
            requesting_user = current
            requesting_user.deactivate()
            SessionService.revoke_all_sessions(requesting_user)
