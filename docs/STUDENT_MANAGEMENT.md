# Student management and admissions

## Records and guardians

Student master data belongs to the institution. Academic placement lives in
StudentEnrollment, so each transfer and promotion preserves the original
session, class, section, date, roll number, and historical status. The
admission date and birth date are checked by the API and database. Guardian
records are reusable across students. Each link stores the relationship and
primary, emergency, and pickup flags. A student has at most one primary
guardian, and the same guardian cannot be linked twice to that student.

The admission-number policy is available on Academic Sessions to authorized
operators. The default is ADM-00001. Prefix and padding can be changed.
Numbers are normalized to uppercase and unique per institution. Manual numbers
can use ASCII letters, digits, periods, hyphens, and underscores. A blank
number at admission requests automatic allocation. The sequence skips used
numbers and rolls back with a failed admission.

## Admission and progression

Use **Admissions → New admission** to fill student information, link or add
guardians, select an active session and class, attach optional scans, and
review before saving. The API commits the student, initial enrollment,
guardians, documents, and audit events in one transaction. Concurrent
placement and admission writes are serialized for this institution. The
policy controls whether sectionless enrollment is allowed.

On the student profile, open Academic history and use **Promote or transfer**
on the latest enrollment. A transfer selects a different section in the same
session and class. Promotion selects a different class in a later session.
Repeating retains the class in a later session. Transfer out, withdrawal, and
graduation close the latest enrollment and update student status. Re-enrollment
creates a new row for a departed student. These operations record the prior
row, successor when applicable, actor, and effective date.

## Documents and privacy

Allowed categories are configurable through STUDENT_DOCUMENT_KINDS. The default
categories cover admission forms, academic records, photographs, transfer
certificates, and other scans. PNG, JPEG, and WebP uploads are decoded, checked
for byte and pixel limits, and re-encoded as PNG with metadata removed.
STUDENT_DOCUMENT_MAX_BYTES defaults to 5 MiB. Documents and portraits are stored
in PostgreSQL and included in authorized database backups. Secure the database
and backups according to the institution's data retention policy.

Document APIs enforce authenticated role permissions and student scoping.
Download names use server-generated UUIDs, and responses prevent caching and
content sniffing. Portrait previews serve only normalized photographs to users
with document read access. Archive disables ordinary access and keeps the
original record and audit history. PDF and office-document parsing are outside
this phase. Scan originals to a supported image format for attachment.

## Reports and access

Filter the Students list by session, class, section or status and use Export
CSV for the selected roster. Admissions exports the filtered admission
register, and profiles offer an enrollment-history CSV and authorized print
view. CSV contains UTF-8 with a BOM and escapes spreadsheet formulas. Exports
and print require explicit permissions, and remain available to authorized
staff after license expiration. Dashboard aggregates use the current session.

Student detail, guardian contacts, and document access are managed separately
in the role matrix. Student master and document writes use the students
feature. Progression uses admissions, and a complete admission requires both
admissions and students. Attendance, fees, and results are labeled future
sections on the profile.

## Verification results

Phase 05 passed 28 tests on isolated PostgreSQL and 21 Angular tests. Chrome
with external DNS blocked exercised academic setup, subject assignments,
guardian linking, image attachment and download, admission, section transfer,
promotion, CSV export, restricted-role denial, and expired-license read-only
behavior. The license clock was advanced inside the isolated verification
process. Real institutional records and deployment credentials stayed in the
development instance throughout these tests.
