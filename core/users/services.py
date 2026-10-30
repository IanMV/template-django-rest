from django.db import transaction

from core.auth.services import SessionService
from core.models.user import User


class UserService:
    @staticmethod
    def list_users(requesting_user: User):
        if requesting_user.is_staff or requesting_user.is_superuser:
            return User.objects.all()
        return User.objects.filter(is_active=True)

    @staticmethod
    def deactivate_user(requesting_user: User):
        with transaction.atomic():
            requesting_user.deactivate()
            SessionService.revoke_all_sessions(requesting_user)
