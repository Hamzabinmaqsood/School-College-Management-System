from django.db import migrations

PERMISSIONS = (
    "accounts.cancel_attendance_leave",
    "accounts.export_attendance",
    "accounts.finalize_attendance",
    "accounts.manage_attendance_calendar",
    "accounts.manage_attendance_settings",
    "accounts.manage_teaching_assignments",
    "accounts.override_attendance_calendar",
    "accounts.print_attendance",
    "accounts.review_attendance_leave",
    "accounts.scope_all_attendance",
    "accounts.view_attendance",
    "accounts.view_attendance_history",
    "attendance.add_attendancecorrection",
    "attendance.add_attendancesession",
    "attendance.add_studentleaverequest",
    "attendance.change_attendancerecord",
    "attendance.view_attendanceholiday",
    "attendance.view_attendancesession",
    "attendance.view_studentleaverequest",
)


def grant_administrator(apps, schema_editor):
    alias = schema_editor.connection.alias
    types = apps.get_model("contenttypes", "ContentType").objects.using(alias)
    permissions = apps.get_model("auth", "Permission").objects.using(alias)
    roles = apps.get_model("accounts", "Role").objects.using(alias)
    role = roles.filter(key="institution-administrator").first()
    for code in PERMISSIONS:
        app, codename = code.split(".", 1)
        model = "role" if app == "accounts" else codename.split("_", 1)[1]
        existing = permissions.filter(content_type__app_label=app, codename=codename).first()
        if not existing:
            kind, _ = types.get_or_create(app_label=app, model=model)
            existing = permissions.create(
                content_type=kind, codename=codename, name=codename.replace("_", " ")
            )
        if role:
            role.group.permissions.add(existing)


def enforce_scope(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE attendance_attendancerecord ADD CONSTRAINT attendance_record_scope_fk "
            "FOREIGN KEY (register_id, session_id, date, mode) REFERENCES "
            "attendance_attendancesession (id, session_id, date, mode)"
        )


def remove_scope(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE attendance_attendancerecord DROP CONSTRAINT attendance_record_scope_fk"
        )


class Migration(migrations.Migration):
    dependencies = [("attendance", "0001_initial")]
    operations = [
        migrations.RunPython(enforce_scope, remove_scope),
        migrations.RunPython(grant_administrator, migrations.RunPython.noop),
    ]
