from django.urls import path

from core.users.views import (
    DeactivateSelfView,
    RevokeAllSessionsView,
    UserListView,
    UserMeView,
)

urlpatterns = [
    path("me/deactivate/", DeactivateSelfView.as_view(), name="deactivate-self"),
    path("me/revoke-sessions/", RevokeAllSessionsView.as_view(), name="revoke-sessions"),
    path("users/me/", UserMeView.as_view(), name="me"),
    path("users/list/", UserListView.as_view(), name="users-list"),
]
