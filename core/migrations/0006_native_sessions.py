from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0005_normalize_user_email")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="session_version",
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
        migrations.DeleteModel(name="UserSession"),
        migrations.DeleteModel(name="AuditLog"),
    ]
