from django.db import transaction

from core.auth.rate_limit import require_current_password
from core.auth.services import SessionService
from core.models.user import User


class UserService:
    @staticmethod
    def list_users():
        return User.objects.filter(is_active=True).order_by("-created_at")

    @staticmethod
    def deactivate_user(requesting_user: User, current_password: str):
        require_current_password(requesting_user, current_password)
        with transaction.atomic():
            requesting_user.deactivate()
            SessionService.revoke_all_sessions(requesting_user)
