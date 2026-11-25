# System Architecture

## 1. Goals

The system is an offline-first, LAN-capable institutional management platform with:

- local PostgreSQL storage;
- no internet dependency for authentication, licensing, or operations;
- support for one Windows workstation or a LAN-hosted Windows/Linux server;
- enforceable backend authorization and license state;
- complete auditing and recoverable data;
- English and Urdu-ready localization;
- configurable school/college terminology and PKR currency.

## 2. Logical architecture

```text
Angular / Angular Material
          |
          | HTTPS or local HTTP on trusted LAN
          v
Django REST API
  |- authentication and CSRF/session or secure token policy
  |- permission and object-level authorization
  |- license enforcement middleware/service
  |- transactional module services
  `- audit and domain event recording
          |
          v
      PostgreSQL
```

The backend is authoritative for authentication, authorization, financial calculations, license validation, audit records, and database integrity. The frontend performs validation for UX only.

## 3. Module boundaries

Suggested Django applications: `core`, `identity`, `academics`, `students`, `guardians`, `staff`, `attendance`, `fees`, `accounts`, `payroll`, `exams`, `timetable`, `library`, `transport`, `reports`, `licensing`, `audit`, and `settings`.

Cross-module operations should call service functions inside transactions rather than bypassing domain rules.

## 4. Deployment topologies

### Standalone Windows

Angular is served by the backend or a local static server. PostgreSQL and Django run as local Windows services. Data stays on the workstation.

### LAN deployment

One designated Windows or Linux server hosts PostgreSQL and Django. Client workstations use a fixed server address and browser. PostgreSQL must bind only to the private LAN address or loopback and must not be exposed to the internet. PostgreSQL TLS, a LAN firewall, and application authentication remain mandatory.

No peer-to-peer database topology is supported in the initial design.

## 5. Identity and tenancy

One physical installation is one institution. The database model uses `institution_id` on institution-owned records. The initial deployment is a single-tenant application with a mandatory institution row. This prevents accidental cross-institution joins while allowing future migration.

## 6. Data lifecycle

Use soft deactivation for students, staff, guardians, classes, and settings where history must remain intact. Use database referential integrity for active links and immutable snapshots for issued records such as receipts and payroll where later master-data edits must not alter past documents.

## 7. Transactions

Financial writes use `transaction.atomic()`, `select_for_update()` where appropriate, database constraints, and idempotency keys for payment/receipt operations. Audit writes occur in the same transaction as the protected action.

## 8. Updates

Updates are versioned, offline packages with signed release metadata. Installation scripts stop services, verify prerequisites and backups, apply migrations, start services, and support a documented rollback. No update requires internet access.

## Local development endpoints

Django development listens on 127.0.0.1:8000 and uses PostgreSQL on 127.0.0.1:5433. The planned Angular server on localhost:4200 will proxy relative /api requests to Django. Frontend integration remains pending.

## Authenticated workspace

Angular uses same-origin Django session APIs. Route guards and sidebar visibility reflect the current grant set. Django rechecks active roles and direct grants on protected operations. Authority changes use a PostgreSQL transaction and a shared lock. An Angular request obtains a masked CSRF token before sending a mutation.

## Offline subscription boundary

The vendor-only CLI signs on a separate workstation. Django verifies the signed payload against a trusted local public-key manifest. PostgreSQL stores the installation identity, signed activations, and clock checkpoint. Angular shows the resulting status. Future business write views compose RBAC with LicensedBusinessWrites.

## Academic and student boundaries

Academics owns session, class, section, and curriculum definitions. Students owns the master register, guardian relationships and private normalized document bytes. Admissions owns session-specific enrollment and progression history. Phase 03 authorization runs before the Phase 04 license gate. Enrollment and related operations lock the existing institution in a transaction.

## Phase 06 attendance

Attendance resolves an eligible roster from dated enrollment and stores a snapshot when opening a draft. Registers use optimistic versions and database locks for concurrent writes.

See [Attendance management](ATTENDANCE_MANAGEMENT.md) for daily and period registers, historical enrollment, leave, calendar, permissions, licensing, APIs and test commands.

## Phase 07 fee management

See [Fee management](FEE_MANAGEMENT.md) for effective-dated structures, billing, PostgreSQL transactions, dynamic financial permissions, the signed fees entitlement and verification commands. Use UTF-8 PostgreSQL.

## Phase 08 examinations

See [Examination management](EXAMINATION_MANAGEMENT.md) for historic rosters, grading, marks verification, publication, corrections and the signed examinations entitlement.

## Phase 09 human resources and payroll

See [Human resources](HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

## Phase 09B boundaries

Attendance and examinations use the same teaching assignment dates. Staff
attendance combines employment contracts, institutional calendar exceptions,
approved leave and clock records. The HR ledger records leave entitlement
changes. Payroll uses immutable overtime approval snapshots and writes its own
salary snapshots during generation. Document review actions modify retention
metadata and retain the private original scan.

Leave accounting keeps a stable leave-type identity. The HR policy resolver
selects institution terms for each period, and the accrual engine applies
contract overrides. New ledger entries link to their applied version. The API
serializes scheduling and ledger mutations using its institution transaction
lock.

Salary structure state transitions run through the HR approval service under
the institution write transaction. The service matches the submitted snapshot
against the current revision at decision and activation. Finalized payroll
continues to read its persisted entry snapshot.

The timetable app owns planning, publication and dated changes. It references
the existing academic, teacher, HR, attendance and examination data rather
than maintaining separate calendars or people. Published read models resolve
one authoritative version per section and date.

Phase 10B resolves the effective day through the same schedule service for
timetable display, workload validation and attendance. The service marks the
source of a cross-date move as inactive and includes the dated replacement
as the effective occurrence. Historical register snapshots remain attached
to their original records.

Timetable successor creation and exception writes use the existing
institution-serialized scheduling transaction. A destination occurrence
projects the effective revision and roster from an immutable source entry
and its dated exception.
