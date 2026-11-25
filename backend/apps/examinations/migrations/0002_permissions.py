from django.db import migrations

PERMISSIONS = ('accounts.approve_exam_results', 'accounts.configure_exam_assessments', 'accounts.correct_exam_results', 'accounts.enter_exam_marks', 'accounts.export_exam_results', 'accounts.manage_exam_grading', 'accounts.manage_exam_schedule', 'accounts.manage_examinations', 'accounts.print_exam_results', 'accounts.publish_exam_results', 'accounts.scope_all_examinations', 'accounts.submit_exam_marks', 'accounts.update_exam_marks', 'accounts.verify_exam_marks', 'accounts.view_class_results', 'accounts.view_exam_analytics', 'accounts.view_exam_marks', 'accounts.view_examinations', 'accounts.view_student_results')

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


class Migration(migrations.Migration):
    dependencies = [("examinations", "0001_initial"), ("fees", "0002_register_fee_permissions")]
    operations = [migrations.RunPython(grant_administrator, migrations.RunPython.noop)]
