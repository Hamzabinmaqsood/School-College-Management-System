from typing import ClassVar

from django.db import migrations

ADMIN = (
    "view_timetable", "manage_timetable", "change_timetable_settings", "submit_timetable",
    "approve_timetable", "publish_timetable", "change_timetable_exceptions", "export_timetable",
    "view_own_timetable",
)


def grant(apps, editor):
    alias = editor.connection.alias
    kind, _ = apps.get_model("contenttypes", "ContentType").objects.using(alias).get_or_create(
        app_label="accounts", model="role"
    )
    types = apps.get_model("auth", "Permission").objects.using(alias)
    roles = apps.get_model("accounts", "Role").objects.using(alias)
    admin = roles.filter(key="institution-administrator").first()
    teacher = roles.filter(key="teacher").first()
    for code in ADMIN:
        permission, _ = types.get_or_create(
            content_type=kind, codename=code, defaults={"name": code.replace("_", " ")}
        )
        if admin:
            admin.group.permissions.add(permission)
        if teacher and code == "view_own_timetable":
            teacher.group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies: ClassVar = [("timetables", "0001_initial")]
    operations: ClassVar = [migrations.RunPython(grant, migrations.RunPython.noop)]
