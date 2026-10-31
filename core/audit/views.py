from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from core.audit.serializers import AuditLogSerializer
from core.models import AuditLog
from core.shared.docs import ForbiddenSerializer, NotAuthenticatedSerializer


class AuditPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AuditListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["audit"],
        summary="List security events (staff only)",
        responses={
            200: inline_serializer(
                "AuditLogPage",
                fields={
                    "count": serializers.IntegerField(),
                    "next": serializers.URLField(allow_null=True),
                    "previous": serializers.URLField(allow_null=True),
                    "results": AuditLogSerializer(many=True),
                },
            ),
            401: NotAuthenticatedSerializer,
            403: ForbiddenSerializer,
        },
    )
    def get(self, request):
        paginator = AuditPagination()
        page = paginator.paginate_queryset(AuditLog.objects.all(), request, view=self)
        return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)
