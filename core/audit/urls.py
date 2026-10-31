from django.urls import path

from core.audit.views import AuditListView

urlpatterns = [path("", AuditListView.as_view(), name="audit-list")]
