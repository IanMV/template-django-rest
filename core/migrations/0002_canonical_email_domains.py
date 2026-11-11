from django.db import migrations


def canonical_email(value):
    value = value.strip().lower()
    local, separator, domain = value.rpartition("@")
    try:
        if separator:
            value = f"{local}@{domain.encode('idna').decode('ascii')}"
    except UnicodeError:
        raise RuntimeError("Resolve invalid email domains before migrating.") from None
    if len(value) > 254:
        raise RuntimeError(
            "Resolve emails exceeding 254 canonical characters before migrating."
        )
    return value


def canonicalize_domains(apps, schema_editor):
    users = apps.get_model("core", "User").objects.using(schema_editor.connection.alias)
    changes = apps.get_model("core", "EmailChange").objects.using(
        schema_editor.connection.alias
    )
    changed_targets = set()
    # Preflight every value before writing; collisions require a human decision, not a merge.
    for pk, email in users.values_list("pk", "email").iterator():
        canonical = canonical_email(email)
        if canonical != email:
            if (
                canonical in changed_targets
                or users.filter(email=canonical).exclude(pk=pk).exists()
            ):
                raise RuntimeError(
                    "Resolve canonical email collisions before migrating; no accounts were merged."
                )
            changed_targets.add(canonical)
    for email in changes.values_list("new_email", flat=True).iterator():
        canonical_email(email)
    for pk, email in users.values_list("pk", "email").iterator():
        canonical = canonical_email(email)
        if canonical != email:
            users.filter(pk=pk).update(email=canonical)
    for pk, email in changes.values_list("pk", "new_email").iterator():
        canonical = canonical_email(email)
        if canonical != email:
            changes.filter(pk=pk).update(new_email=canonical)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(canonicalize_domains, migrations.RunPython.noop)]
