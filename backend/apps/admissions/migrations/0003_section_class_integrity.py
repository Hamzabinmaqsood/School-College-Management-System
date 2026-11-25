from django.db import migrations


def add_constraint(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE admissions_studentenrollment ADD CONSTRAINT enrollment_section_matches_class "
            "FOREIGN KEY (section_id, academic_class_id) REFERENCES academics_section (id, academic_class_id)"
        )


def remove_constraint(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "ALTER TABLE admissions_studentenrollment DROP CONSTRAINT enrollment_section_matches_class"
        )


class Migration(migrations.Migration):
    dependencies = [("admissions", "0002_initial")]
    operations = [migrations.RunPython(add_constraint, remove_constraint)]
