from django.db import migrations, models
from django.db.models.functions import Lower, Trim


def normalize_emails(apps, schema_editor):
    users = apps.get_model("core", "User").objects.using(schema_editor.connection.alias)
    collisions = (
        users.order_by()
        .annotate(canonical_email=Lower(Trim("email")))
        .values("canonical_email")
        .annotate(total=models.Count("pk"))
        .filter(total__gt=1)
    )
    if collisions.exists():
        raise RuntimeError(
            "Email identity collisions exist; resolve them before migrating."
        )
    users.update(email=Lower(Trim("email")))
    apps.get_model("core", "EmailChange").objects.using(
        schema_editor.connection.alias
    ).update(new_email=Lower(Trim("new_email")))


class Migration(migrations.Migration):
    dependencies = [("core", "0004_auditlog")]

    operations = [
        migrations.RunPython(normalize_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(email=Lower(Trim("email"))),
                name="core_user_email_canonical",
            ),
        ),
    ]
