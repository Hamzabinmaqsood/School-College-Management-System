from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION examinations_check_mark_scope() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM examinations_markssubmission submission
                JOIN examinations_examassessmentcomponent component ON component.id = submission.component_id
                JOIN examinations_examinationsubject subject ON subject.id = component.subject_id
                JOIN examinations_studentexamregistration roster ON roster.id = NEW.registration_id
                WHERE submission.id = NEW.submission_id
                  AND subject.group_id = roster.group_id
                  AND submission.section_id IS NOT DISTINCT FROM roster.section_id
                  AND NOT roster.excluded
                  AND (NEW.obtained IS NULL OR NEW.obtained <= component.maximum)
            ) THEN
                RAISE EXCEPTION 'Mark violates assessment scope or maximum'
                    USING ERRCODE = '23514', CONSTRAINT = 'exam_mark_scope';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    schema_editor.execute("""
        CREATE TRIGGER examinations_mark_scope
        BEFORE INSERT OR UPDATE OF submission_id, registration_id, obtained
        ON examinations_studentassessmentmark FOR EACH ROW
        EXECUTE FUNCTION examinations_check_mark_scope();
    """)


def remove(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP TRIGGER examinations_mark_scope ON examinations_studentassessmentmark"
        )
        schema_editor.execute("DROP FUNCTION examinations_check_mark_scope()")


class Migration(migrations.Migration):
    dependencies = [("examinations", "0002_permissions")]
    operations = [migrations.RunPython(install, remove)]
