# Initial PostgreSQL Database Design

## 1. Core conventions

- UUID primary keys for distributed-safe identifiers.
- `created_at`, `updated_at`, `created_by_id`, and `updated_by_id` on mutable domain records.
- PostgreSQL `timestamptz` for UTC timestamps and explicit date fields for academic/business dates.
- `PKR` represented as integer minor units (paisa) or PostgreSQL `NUMERIC(19,2)` for monetary values.
- No destructive deletes for historical records.
- Soft deletion or status fields unless a strict privacy-retention policy permits deletion.

## 2. Initial entities

### Institution and settings

- `institutions`: id, name, code, institution_type, timezone, locale, currency, branding
- `academic_sessions`: id, institution_id, name, start_date, end_date, is_current
- `settings`: institution_id, key, value JSONB, value_type

### Identity and permissions

- `users`: id, institution_id, username, password_hash, full_name, is_active
- `roles`: id, institution_id, name, description
- `permissions`: code, module, action, description
- `role_permissions`: role_id, permission_id
- `user_roles`: user_id, role_id
- `user_sessions`: id, user_id, issuer, expires_at, revoked_at

Dynamic role and permission checks must evaluate database-backed `role_permissions` and optional object-scoped grants. Django authorization is the final decision point.

### People

- `persons`: id, institution_id, type, national identifiers, encrypted or restricted PII fields as applicable
- `students`: id, person_id, institution_id, admission_number, admission_date, status
- `guardians`: id, person_id, institution_id, contact fields
- `student_guardians`: student_id, guardian_id, relationship, is_primary
- `staff`: id, person_id, institution_id, employee_number, designation, employment status

### Academics

- `grades` or `classes`: id, institution_id, name, sequence
- `sections`: id, institution_id, class_id, name, session_id, capacity
- `subjects`: id, institution_id, code, name
- `class_subjects`: class_id, subject_id
- `section_subjects`: section_id, subject_id
- `student_enrollments`: id, student_id, session_id, section_id, roll_number, status
- `subjects` and enrollments carry historical session/class relationships.

### Attendance

- `attendance_sessions`: id, institution_id, session date, section/class/staff scope
- `student_attendance`: id, attendance_session_id, student_id, status, remarks
- `staff_attendance`: id, institution_id, staff_id, date, status, check-in/out

Enforce one status per student per attendance session and per staff per date.

### Fees and accounting

- `fee_structures`: id, institution_id, session_id, class_id, name
- `fee_items`: id, fee_structure_id, name, amount
- `fee_charges`: id, institution_id, student_id, session_id, fee_item_id, amount, due_date
- `fee_payments`: id, institution_id, student_id, amount, method, received_at, idempotency_key
- `fee_allocations`: payment_id, charge_id, amount
- `receipts`: id, payment_id, receipt_number, immutable issued snapshot
- `accounts`: id, institution_id, code, name, account_type
- `transactions`: id, institution_id, account_id, debit, credit, reference_type, reference_id
- `expenses`: id, institution_id, account_id, amount, vendor, date, status

Financial totals use database constraints and atomic posting. Reversals create opposite entries rather than modifying posted transactions.

### Payroll

- `salary_structures`, `salary_components`, `payroll_runs`, `payroll_items`, `payroll_payments`.

### Examinations

- `exams`, `exam_terms`, `exam_subjects`, `exam_schedule`, `marks_entries`, `result_snapshots`, `grade_scales`.

Prevent duplicate marks entries and snapshot approved results.

### Operations

- `timetable_slots`, `timetable_entries`, `library_items`, `library_copies`, `library_loans`, `routes`, `vehicles`, `transport_assignments`.

### Audit and licensing

- `audit_logs`: immutable event records with actor, action, object type/id, before/after JSON, IP, timestamp
- `installations`: stable installation_id, institution, public_key_id
- `license_records`: payload hash, signed payload, validity dates, grace, last_known_valid clock, activated_at
- `license_clock_observations`: observed_at, system_at, monotonic or server-derived timestamp

No license feature may depend on record deletion or record encryption.

## 3. Referential integrity

Use foreign keys, `ON DELETE RESTRICT` for historical records, soft deletion for mutable masters, and database checks for positive amounts, date ranges, unique active codes, and status transitions.

## 4. Index strategy

Index foreign keys not automatically indexed, `(institution_id, status)`, academic `(session_id, section_id)`, attendance `(student_id, date)`, fee `(student_id, due_date)`, audit `(institution_id, timestamp)`, and unique constraints for admission/receipt/payroll codes.

## 5. Initial migration sequence

Institutions and settings, users/roles/permissions, people and students/guardians/staff, academic structure, attendance and fee/accounting foundations, payroll/exams/timetable/library/transport, audit, and licensing.

## Local development database

PostgreSQL 18.6 listens on 127.0.0.1:5433. Run bash scripts/setup-database.sh in Ubuntu to provision school_management_db and its dedicated owner school_management_app. The script uses the existing password from backend/.env and sets NOSUPERUSER, NOCREATEDB, and NOCREATEROLE.

## Authentication and institution schema

The accounts migrations add user contact and password-change fields, session revocation tracking, role metadata linked to Django Groups, temporary login-attempt counters, and an institution singleton. A unique constant guarded by a check constraint enforces the singleton. Logo bytes are stored as a normalized PNG in PostgreSQL and included in database backups. Existing groups retain their assignments and are linked to role metadata.

## Subscription tables

The licensing migrations add InstallationIdentity, linked one-to-one to the existing institution, and append-only LicenseActivation records keyed by the signed UUID. The current activation is switched under an installation lock. Signed metadata remains in the token, and audit events use the existing audit table. Existing institutions receive stable identifiers during migration.

## Phase 05 constraints

Academic codes and admission numbers are unique within their documented scope. PostgreSQL partial indexes enforce one current session, one primary guardian, and one active enrollment per student and session. Active roll numbers are unique within their session and group including unsectioned students. A composite foreign key enforces section and class consistency. Historical links use protective foreign keys.

## Phase 06 attendance

AttendanceSession owns frozen roster slots in AttendanceRecord. A PostgreSQL composite foreign key protects the copied session, date and mode. Partial unique indexes protect daily student and period register identity.

See [Attendance management](ATTENDANCE_MANAGEMENT.md) for daily and period registers, historical enrollment, leave, calendar, permissions, licensing, APIs and test commands.

## Phase 07 fee management

See [Fee management](FEE_MANAGEMENT.md) for effective-dated structures, billing, PostgreSQL transactions, dynamic financial permissions, the signed fees entitlement and verification commands. Use UTF-8 PostgreSQL.

## Phase 08 examinations

See [Examination management](EXAMINATION_MANAGEMENT.md) for historic rosters, grading, marks verification, publication, corrections and the signed examinations entitlement.

## Phase 09 human resources and payroll

See [Human resources](HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

## Phase 09B schema

Apply attendance migration 0003 and HR migrations 0006 through 0011. They add
assignment date bounds, shift breaks and tolerances, document review decisions,
overtime policies and requests, leave-policy and leave-ledger data, and the
optional unpaid leave deduction rate. Migration 0011 adds department schedule
templates and contract leave entitlement overrides. Employee records retain their IDs.
An overtime request references a unique staff attendance record. A leave
transaction key is unique per employee and leave type.

Migration `hr.0012_leave_policy_versions` adds a protected leave policy version
relation and a unique leave-type/effective-start pair. Published start dates
form consecutive intervals with exclusive upper bounds. The migration backfills
one baseline per existing leave type. Ledger provenance columns are additive.
Existing rows retain their amounts, dates, posting keys, and unknown version
reference.

Migration `hr.0013_salary_structure_approval` adds revision, optional effective
dates, creator, and legacy markers to salary structures. An approval record
is unique per structure revision and stores the submitted terms and actors.
Existing active structures keep their active flag and are marked as legacy.
The migration inserts no approval decisions and leaves assignments, components,
payroll entries and payments intact.

Timetables adds settings, shifts, periods, rooms, availability, plans, versions,
entries, weekly subject requirements and daily exceptions. The unique plan
scope is session and section. Entries are unique per version, day and period.
A supersession boundary preserves the original published version dates.
Attendance 0004 adds an optional timetable snapshot to new matching registers.

Timetable 0004 adds teacher preference type and priority, effective workload
policies, and the destination date on a dated exception. Timetable 0005 adds
teaching groups and explicit enrollment membership. Separate conditional
slot uniqueness preserves full-section identities while allowing validated
parallel option groups.

### Timetable roster history

An optional group has one root per academic session, section and subject.
A successor has one predecessor and an effective timetable revision.
Root rows and old memberships are retained. Dated exceptions can store the
effective destination revision and group while keeping the original entry
foreign key. Legacy dated exceptions use their original entry's revision.
