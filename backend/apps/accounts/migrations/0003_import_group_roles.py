from django.db import migrations


def import_groups(apps, schema_editor):
    groups = apps.get_model("auth", "Group")
    roles = apps.get_model("accounts", "Role")
    database = schema_editor.connection.alias
    for group_id in groups.objects.using(database).values_list("pk", flat=True).iterator():
        roles.objects.using(database).get_or_create(group_id=group_id)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_loginattempt_user_password_change_required_and_more")]
    operations = [migrations.RunPython(import_groups, migrations.RunPython.noop)]
