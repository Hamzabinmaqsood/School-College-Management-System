from django.db import migrations

PERMISSIONS = ('accounts.approve_fee_adjustment', 'accounts.approve_fee_concession', 'accounts.approve_fee_refund', 'accounts.approve_fee_write_off', 'accounts.collect_fees', 'accounts.export_fee_reports', 'accounts.generate_fee_invoices', 'accounts.manage_fee_adjustments', 'accounts.manage_fee_settings', 'accounts.print_fee_challan', 'accounts.print_fee_receipt', 'accounts.reverse_fee_payment', 'accounts.view_fee_reports', 'accounts.view_fees', 'accounts.void_fee_invoice', 'fees.change_feecategory', 'fees.change_feestructure', 'fees.change_studentconcession', 'fees.change_studentfeeassignment', 'fees.view_feeadjustment', 'fees.view_feecategory', 'fees.view_feeinvoice', 'fees.view_feepayment', 'fees.view_feerefund', 'fees.view_feestructure', 'fees.view_studentconcession', 'fees.view_studentfeeassignment')

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
    dependencies = [("fees", "0001_initial"), ("attendance", "0002_register_attendance_permissions")]
    operations = [migrations.RunPython(grant_administrator, migrations.RunPython.noop)]
