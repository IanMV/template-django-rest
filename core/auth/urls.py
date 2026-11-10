from django.urls import path

from core.auth.views import LoginView, LogoutView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("me/logout/", LogoutView.as_view(), name="logout"),
]
