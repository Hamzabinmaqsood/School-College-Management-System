# School and College Management System

This repository will contain a production-ready, offline-first school and college management system. The initial phase establishes the environment, architecture, database design, security model, licensing model, and implementation roadmap.

## Repository layout

- `backend/` - Django and Django REST Framework application
- `frontend/` - Angular application
- `vendor-tools/license-generator/` - isolated, vendor-only license signing tool
- `deployment/` - Windows, LAN, Linux, service, and backup configuration
- `scripts/` - controlled administrative and maintenance scripts
- `tests/` - integration and cross-module test assets
- `docs/` - architecture and operational documentation

Institutional data is local. No cloud service is required for normal operation.

## Run locally in Ubuntu/WSL

With the existing Python environment, PostgreSQL database, and Linux Node.js installed, run:

    cd ~/school-management-system
    source "$HOME/.nvm/nvm.sh"
    nvm use
    (cd frontend && npm ci)
    bash scripts/start-dev.sh

Open http://localhost:4200/login. The dashboard shows live connectivity and empty states for planned modules. Django Admin is available at http://127.0.0.1:8000/admin/ for staff superusers.

Before the first sign-in on an upgraded or fresh installation:

    .venv/bin/python -m pip install -r backend/requirements/development.txt
    .venv/bin/python backend/manage.py migrate
    .venv/bin/python backend/manage.py seed_roles
    .venv/bin/python backend/manage.py setup_admin

Sign in and complete institution setup. See [local authentication](docs/AUTHENTICATION.md) and [roles and permissions](docs/ROLE_PERMISSIONS.md).

To run around local port conflicts:

    DJANGO_PORT=8001 ANGULAR_PORT=4201 bash scripts/start-dev.sh

See [environment setup](docs/ENVIRONMENT_SETUP.md) for verification and offline deployment.

## Offline subscriptions

Complete institution setup, then open Subscription to get the institution
and installation IDs. Install the vendor's trusted public-key manifest on
the server and set LICENSE_PUBLIC_KEYS_FILE before starting the services.
Use Activation to import or paste a vendor-issued license. [Licensing guide](docs/LICENSING.md)

## Academic operations

Apply migrations and run seed_roles after upgrading. Open Academic Sessions
and configure an active current term, then create classes, sections, and
subjects. Admissions guides staff through student registration and placement.
These writes require the corresponding signed license features and role grants.
See [Academic management](docs/ACADEMIC_MANAGEMENT.md) and
[Student management](docs/STUDENT_MANAGEMENT.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Database design](docs/DATABASE_DESIGN.md)
- [Offline licensing](docs/LICENSING.md)
- [API conventions](docs/API_CONVENTIONS.md)
- [Security](docs/SECURITY.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)

## Security boundary

The private Ed25519 signing key belongs only in vendor-controlled storage and must never be included in customer builds, source repositories, database backups, or the customer application. This repository must contain no production signing key.

## Phase 06 attendance

Open Attendance after sign-in. Use the role matrix and Attendance settings to grant teacher actions and assign teaching groups. An active signed license with the attendance feature enables granted actions.

See [Attendance management](docs/ATTENDANCE_MANAGEMENT.md) for daily and period registers, historical enrollment, leave, calendar, permissions, licensing, APIs and test commands.

## Phase 07 fee management

See [Fee management](docs/FEE_MANAGEMENT.md) for effective-dated structures, billing, PostgreSQL transactions, dynamic financial permissions, the signed fees entitlement and verification commands. Use UTF-8 PostgreSQL.

## Phase 08 examinations

See [Examination management](docs/EXAMINATION_MANAGEMENT.md) for historic rosters, grading, marks verification, publication, corrections and the signed examinations entitlement.

## Phase 09 human resources and payroll

See [Human resources](docs/HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

## Phase 09B development

From the project root in Ubuntu WSL, apply schema updates and start the existing
development stack.

```bash
.venv/bin/python backend/manage.py migrate --noinput
bash scripts/start-dev.sh
```

Open http://localhost:4200/hr/attendance for the staff calendar or
http://localhost:4200/hr/payroll for compensation. Django readiness is available
at http://127.0.0.1:8000/api/v1/ready/. The existing PostgreSQL configuration
continues to use port 5433. See [HR workflows](docs/HR_MANAGEMENT.md) and
[payroll](docs/PAYROLL_MANAGEMENT.md).

Phase 09C acceptance evidence and open scenarios are tracked in the
[Phase 09 acceptance report](docs/PHASE_09_ACCEPTANCE_REPORT.md).

Phase 09D added teacher attendance and marks-entry browser evidence and reran
the complete regression suites. The acceptance report lists the remaining
authorization, mobile, calendar, leave, and retention scenarios.

Phase 09E adds reusable browser acceptance tests under `frontend/tests/browser/phase09`.

If Django or Angular reports an occupied port, the startup scripts show the
listener and probe the existing school application. Reuse a healthy instance
or specify two available ports. The Angular proxy follows `DJANGO_PORT`.

```bash
DJANGO_PORT=8012 ANGULAR_PORT=4212 bash scripts/start-dev.sh
bash frontend/tests/browser/phase09/run.sh
```

Phase 09G separates the five-role read matrix from the desktop and mobile
workflow suite. Run `SMS_PHASE09_MATRIX=1 bash frontend/tests/browser/phase09/run.sh`
with the browser prerequisites installed. The launcher verifies database and
proxy isolation before passing disposable credentials to Playwright.

Phase 09H adds employee create and edit authorization and live edit revocation
to the isolated matrix. Import passing evidence with
`node frontend/tests/browser/phase09/update-security-evidence.mjs <results.json> employee`
or use `exam` for the corresponding examination scope report.

Phase 09I adds isolated payroll and teacher-write browser suites. Set
`SMS_PHASE09_FINANCE=desktop` or `SMS_PHASE09_TEACHER=desktop` when running
`bash frontend/tests/browser/phase09/run.sh`. Use `mobile` for the 390 px
workflow. See the acceptance report for coverage and evidence locations.

Phase 09J adds salary draft editing and isolated revision acceptance. The
desktop run checks the five configured roles, salary audit records and live
salary setup revocation. The mobile run covers leave accrual, the staff
calendar and document retention. See the
[Phase 09J evidence and remaining IDs](docs/PHASE_09_ACCEPTANCE_REPORT.md#phase-09j)
for current acceptance status.

```bash
SMS_PHASE09_REVISIONS=desktop SMS_PHASE09_FINANCE=desktop SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_REVISIONS=mobile SMS_PHASE09_FINANCE=mobile bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_TEACHER=desktop bash frontend/tests/browser/phase09/run.sh
```

Phase 09K tests the five-role HR workflow matrix, payroll authorization,
and mobile teaching assignment and overtime workflows. Run the acceptance
projects from the repository root after installing the browser prerequisites.
See the [Phase 09K report](docs/PHASE_09_ACCEPTANCE_REPORT.md#phase-09k).

```bash
SMS_PHASE09_WORKFLOWS=desktop SMS_PHASE09_FINANCE=desktop SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_WORKFLOWS=mobile bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_FINANCE=desktop bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_FINANCE=mobile SMS_PHASE09_REVISIONS=mobile bash frontend/tests/browser/phase09/run.sh
```

Phase 09L adds future-dated leave policy revisions and versioned accrual
provenance. Apply migrations with `.venv/bin/python backend/manage.py migrate`
before starting the upgraded application. The migration keeps existing ledger
amounts and leave-type references intact. Run the isolated acceptance suites
sequentially from the repository root.

```bash
SMS_PHASE09_LEAVE=desktop bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_LEAVE=mobile SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
```

See the [Phase 09L acceptance report](docs/PHASE_09_ACCEPTANCE_REPORT.md#phase-09l).

Phase 09M adds explicit salary structure approval. Apply
`hr.0013_salary_structure_approval` with the normal Django migration command.
On the **Salary structures** page, submit the draft, review the exact revision
in the approval queue, and activate after an approval decision. Run the
isolated acceptance tests sequentially.

```bash
SMS_PHASE09_APPROVAL=desktop SMS_PHASE09_FINANCE=desktop bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_APPROVAL=mobile SMS_PHASE09_FINANCE=mobile bash frontend/tests/browser/phase09/run.sh
```

Phase 10 introduces the [Timetable workspace](docs/TIMETABLE_MANAGEMENT.md).
It uses the `timetables` signed feature for writes and installs through the
normal Django migration workflow. See the timetable guide for the isolated
browser commands and operational upgrade prerequisites.

Phase 10B adds optional teaching groups, teacher preferences and workload
policies, dated relocations and dedicated reports. See the
[Phase 10 acceptance report](docs/PHASE_10_ACCEPTANCE_REPORT.md) for current
verification and the operational backup gate.


## Timetable acceptance

Phase 10C verification, the machine-readable checklist, and the current operational migration status are recorded in the [Phase 10 acceptance report](docs/PHASE_10_ACCEPTANCE_REPORT.md). Start development with `bash scripts/start-dev.sh`. Operational upgrades require the [encrypted backup and restore procedure](docs/DEPLOYMENT.md) and separate authorization to apply migrations.

The [Phase 10D acceptance report](docs/PHASE_10_ACCEPTANCE_REPORT.md#phase-10d)
tracks timetable verification and operational deployment readiness.

See the [Phase 10E acceptance record](docs/PHASE_10_ACCEPTANCE_REPORT.md#phase-10e)
for timetable changes, current evidence, and the operational handoff.

See the [Phase 10F acceptance record](docs/PHASE_10_ACCEPTANCE_REPORT.md#phase-10f)
for successor rosters, moves across timetable revisions, and deployment status.
