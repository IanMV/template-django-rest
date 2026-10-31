from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_remove_usersession_location")]

    operations = [
        migrations.AddField(
            model_name="usersession",
            name="remember_me",
            field=models.BooleanField(
                default=False,
                help_text="Refresh tokens remain valid for seven days of inactivity.",
            ),
        ),
    ]
