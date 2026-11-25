from django.db import migrations


def initialize(apps, schema_editor):
    database = schema_editor.connection.alias
    identities = apps.get_model("licensing", "InstallationIdentity").objects.using(database)
    institutions = apps.get_model("accounts", "Institution").objects.using(database)
    for institution_id in institutions.values_list("id", flat=True).iterator():
        identities.get_or_create(institution_id=institution_id)

    content_type, _ = apps.get_model("contenttypes", "ContentType").objects.using(database).get_or_create(
        app_label="accounts", model="role",
    )
    permission, _ = apps.get_model("auth", "Permission").objects.using(database).get_or_create(
        content_type=content_type, codename="manage_subscription", defaults={"name": "Manage subscription"},
    )
    role = apps.get_model("accounts", "Role").objects.using(database).filter(
        key="institution-administrator",
    ).first()
    if role:
        role.group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("licensing", "0001_initial"), ("accounts", "0003_import_group_roles")]
    operations = [migrations.RunPython(initialize, migrations.RunPython.noop)]
