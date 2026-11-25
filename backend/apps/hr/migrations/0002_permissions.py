from django.db import migrations

PERMISSIONS = ('accounts.add_employee', 'accounts.approve_payroll', 'accounts.approve_salary_advance', 'accounts.approve_staff_leave', 'accounts.change_employee', 'accounts.correct_payroll', 'accounts.correct_staff_attendance', 'accounts.export_hr', 'accounts.export_payroll', 'accounts.finalize_payroll', 'accounts.generate_payroll', 'accounts.manage_employee_documents', 'accounts.manage_hr_registry', 'accounts.manage_salary_setup', 'accounts.mark_staff_attendance', 'accounts.pay_salary', 'accounts.print_payslip', 'accounts.request_staff_leave', 'accounts.review_payroll', 'accounts.submit_payroll', 'accounts.view_employee_documents', 'accounts.view_payroll', 'accounts.view_salary_setup', 'accounts.view_staff', 'accounts.view_staff_attendance', 'accounts.view_staff_leave', 'accounts.view_teachers')


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
    dependencies = [("hr", "0001_initial"), ("examinations", "0002_permissions")]
    operations = [migrations.RunPython(grant_administrator, migrations.RunPython.noop)]
