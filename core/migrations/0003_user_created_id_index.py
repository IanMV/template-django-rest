from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_canonical_email_domains")]
    operations = [
        migrations.AddIndex(
            model_name="user",
            index=models.Index(
                fields=["-created_at", "-id"], name="core_user_created_id_idx"
            ),
        ),
    ]
