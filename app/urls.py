from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/docs/", include("core.shared.urls")),
    path("api/", include("core.auth.urls")),
    path("api/", include("core.users.urls")),
    path("api/registration/", include("core.registration.urls")),
    path("api/password-reset/", include("core.password_reset.urls")),
    path("api/email-change/", include("core.email_change.urls")),
]
