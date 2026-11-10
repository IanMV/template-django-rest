from django.urls import path

from core.users.views import (
    DeactivateSelfView,
    UserListView,
    UserMeView,
)

account_urlpatterns = [
    path("me/deactivate/", DeactivateSelfView.as_view(), name="deactivate-self"),
]

profile_urlpatterns = [
    path("users/me/", UserMeView.as_view(), name="me"),
    path("users/list/", UserListView.as_view(), name="users-list"),
]

urlpatterns = account_urlpatterns + profile_urlpatterns
