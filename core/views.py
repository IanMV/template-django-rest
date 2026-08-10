from django.contrib.auth import get_user_model
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

from core.serializers import UserCreateSerializer, UserListRetrieveSerializer

# Create your views here.


User = get_user_model()


class UserViewSet(ModelViewSet):
    queryset = User.objects.all()
    permission_classes = AllowAny

    def get_serializer_class(self):
        if self.action in ("retrieve", "list"):
            return UserListRetrieveSerializer
        if self.action == "create":
            return UserCreateSerializer
        return UserListRetrieveSerializer
