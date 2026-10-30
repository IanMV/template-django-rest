from django.urls import path

from core.auth.session_views import UserSessionsDeactivateView, UserSessionsGetView
from core.auth.views import CustomTokenRefreshView, LoginView, LogoutView

login_urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("me/logout/", LogoutView.as_view(), name="logout"),
]

session_urlpatterns = [
    path("sessions/", UserSessionsGetView.as_view(), name="user-sessions-list"),
    path(
        "sessions/<int:session_id>/",
        UserSessionsDeactivateView.as_view(),
        name="user-sessions-deactivate",
    ),
]

refresh_urlpatterns = [
    path("refresh/", CustomTokenRefreshView.as_view(), name="refresh"),
]

urlpatterns = login_urlpatterns + session_urlpatterns + refresh_urlpatterns
