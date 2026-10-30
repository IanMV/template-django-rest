from django.contrib import admin
from django.urls import include, path

from core.auth import urls as auth_urls
from core.users import urls as users_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/docs/", include("core.shared.urls")),
    path("api/", include(auth_urls.login_urlpatterns)),
    path("api/", include(users_urls.account_urlpatterns)),
    path("api/", include(auth_urls.session_urlpatterns)),
    path("api/registration/", include("core.registration.urls")),
    path("api/password-reset/", include("core.password_reset.urls")),
    path("api/email-change/", include("core.email_change.urls")),
    path("api/", include(auth_urls.refresh_urlpatterns)),
    path("api/", include(users_urls.profile_urlpatterns)),
]
