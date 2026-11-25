from django.db import migrations


PERMISSIONS = (
    'academics.add_academicclass',
    'academics.add_academicsession',
    'academics.add_classsubject',
    'academics.add_section',
    'academics.add_subject',
    'academics.change_academicclass',
    'academics.change_academicsession',
    'academics.change_classsubject',
    'academics.change_section',
    'academics.change_subject',
    'academics.view_classsubject',
    'accounts.archive_student_documents',
    'accounts.export_admissions',
    'accounts.export_students',
    'accounts.manage_admissions_policy',
    'accounts.manage_guardian_links',
    'accounts.print_students',
    'accounts.progress_students',
    'accounts.view_academics',
    'accounts.view_admissions',
    'accounts.view_classes',
    'accounts.view_sections',
    'accounts.view_sessions',
    'accounts.view_student_details',
    'accounts.view_students',
    'accounts.view_subjects',
    'admissions.add_studentenrollment',
    'students.add_guardian',
    'students.add_student',
    'students.add_studentdocument',
    'students.change_guardian',
    'students.change_student',
    'students.view_guardian',
    'students.view_studentdocument',
)


def grant_administrator(apps, schema_editor):
    alias = schema_editor.connection.alias
    types = apps.get_model("contenttypes", "ContentType").objects.using(alias)
    permissions = apps.get_model("auth", "Permission").objects.using(alias)
    roles = apps.get_model("accounts", "Role").objects.using(alias)
    role = roles.filter(key="institution-administrator").first()
    for code in PERMISSIONS:
        app, codename = code.split(".", 1)
        model = codename.split("_", 1)[-1]
        if app == "accounts":
            model = "role"
        kind, _ = types.get_or_create(app_label=app, model=model)
        existing = permissions.filter(content_type__app_label=app, codename=codename).first()
        if not existing:
            existing = permissions.create(content_type=kind, codename=codename, name=codename.replace("_", " "))
        if role:
            role.group.permissions.add(existing)


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"), ("students", "0001_initial"), ("admissions", "0002_initial"),
        ("licensing", "0002_initialize_licensing"),
    ]
    operations = [migrations.RunPython(grant_administrator, migrations.RunPython.noop)]
