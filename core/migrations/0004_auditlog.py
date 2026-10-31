import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_usersession_remember_me"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_uuid_snapshot", models.UUIDField(blank=True, null=True)),
                ("event_type", models.CharField(db_index=True, max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, db_index=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=512)),
                ("session_id", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("SUCCESS", "Success"), ("FAILURE", "Failure"), ("BLOCKED", "Blocked")], max_length=32)),
                ("details_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="auditlog", index=models.Index(fields=["event_type", "created_at"], name="core_auditl_event_t_f36ba9_idx")),
        migrations.AddIndex(model_name="auditlog", index=models.Index(fields=["ip_address", "created_at"], name="core_auditl_ip_addr_664863_idx")),
    ]
