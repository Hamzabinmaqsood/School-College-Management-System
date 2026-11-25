# Implementation Roadmap

## Phase 01: Architecture and environment

Deliverables:

- environment assessment;
- repository structure;
- architecture and database documents;
- security, licensing, API, deployment, and setup documents;
- no business modules or signing keys.

Acceptance criteria:

- all required Phase 01 documents exist;
- no existing files were overwritten;
- no production secrets were added;
- repository layout is clear and vendor signing material is isolated.

## Phase 02: Foundation

Phase 02C completed the local initialization and integration checks. PostgreSQL migrations, Django and Angular checks, the dashboard API proxy, and the offline production build passed. Phase 03 extends the foundation with local authentication, institution setup, user administration, role permissions, and audit review.

Deliverables:

- Django project, DRF, PostgreSQL configuration, environment templates;
- Angular workspace and Angular Material baseline;
- authentication, institution, role/permission foundation;
- migration and test harness;
- audit and license service skeleton.

Acceptance criteria:

- backend and frontend start locally;
- database migrations pass on clean PostgreSQL;
- login/logout and permission denial tests pass;
- secrets are supplied by environment and excluded from Git.

## Phase 03: Authentication and institution administration

Complete. Authenticated Angular routes, institution branding and settings,
user and dynamic role management, permission enforcement, and audit review
passed the automated backend and frontend checks and the isolated browser workflow.
Operational student and finance records remain future work.

## Phase 04: Offline subscription licensing

Complete. Vendor issuance, installation binding, offline activation and renewal,
key rotation support, lifecycle enforcement, audit, and authenticated Angular
subscription pages passed the Phase 04 verification workflow. Ordinary business modules are scheduled in later phases.

## Phase 05: Academic structure, admissions and student management

Complete. Academic sessions, classes, sections, subjects, and curriculum
assignments passed the isolated PostgreSQL, Angular, and browser workflow. Student masters, guardians, admissions, progression, private
documents, authorized exports, and current-session dashboard metrics share the
existing offline licensing and roles.

## Phase 06: Student attendance and leave management

Includes daily and period registers, historical roster snapshots, audited
corrections, leave review, calendar policy and teaching-scope restrictions.
Analytics, student history and offline exports use stored attendance records.
See [Attendance management](ATTENDANCE_MANAGEMENT.md).

## Phase 07: Student fee management

Includes billing, collection, printable receipts and challans, controlled corrections,
student balances and fee reporting. See [Fee management](FEE_MANAGEMENT.md).

## Planned: General accounting

Deliverables:

- fee structures, charges, payments, receipts;
- chart of accounts, income/expenses;
- accounting entries and reconciliation.

Acceptance criteria:

- no payment can be posted twice;
- balances reconcile by account and student;
- atomic posting and receipt immutability tests pass.

## Phase 08: Examinations and academic results

See [Examination management](EXAMINATION_MANAGEMENT.md) and [Grading and results](GRADING_AND_RESULTS.md).

## Planned: School operations

Deliverables:

- regular timetable;
- library, transport, and operational reporting.

Acceptance criteria:

- duplicate marks blocked;
- approved result snapshots unchanged by later entry edits;
- timetable and resource conflict tests pass.

## Planned: Licensing and release operations

Deliverables:

- Ed25519 customer verifier;
- separate vendor generator;
- clock-observation and write enforcement;
- backup/restore and offline update package;
- Windows service and LAN deployment scripts.

Acceptance criteria:

- cryptographic and expired-license tests pass;
- reads/export/backup/renewal remain available after expiry;
- private key absent from customer package and repository;
- restore test passes.

## Planned: Hardening and acceptance

Deliverables:

- localization readiness, responsive UI, full reports;
- security review, privacy controls, load testing;
- backup restore drills;
- Windows/LAN/Linux deployment validation;
- automated CI for backend and frontend.

Acceptance criteria:

- critical security tests pass;
- documented recovery objectives are demonstrated;
- no internet dependency in normal operation;
- signed release and rollback procedures tested.

## Phase 09 human resources and payroll

See [Human resources](HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

## Phase 09B HR operations

Phase 09B adds dated teaching scope, staff calendar views, leave accrual and
ledger transactions, overtime approval and payroll integration, and document
retention reviews. Departments can supply schedule templates and contracts can
override leave entitlement. Full browser workflow coverage remains open.

Phase 09C verified the administrator assignment lifecycle in desktop Chrome
and added an assignment history panel. Phase 09 remains open pending the
remaining scenarios in the [acceptance report](PHASE_09_ACCEPTANCE_REPORT.md).
Phase 10 has not started.

Phase 09D verified the teacher attendance and marks workflows on desktop and
the expanded staff calendar at desktop and mobile widths. Phase 09 remains
open pending the scenarios in the [acceptance report](PHASE_09_ACCEPTANCE_REPORT.md).

Phase 09E introduces an isolated Playwright suite and a machine-readable checklist. Phase 09 remains open pending full acceptance.

Phase 09F adds development port conflict diagnostics and expands isolated
acceptance coverage. Phase 09 closure remains gated by the outstanding checks
in the [acceptance report](PHASE_09_ACCEPTANCE_REPORT.md).

Phase 09G expands the isolated read matrix, role revocation and examination
authorization checks. The Phase 09 acceptance checklist remains the source
for open write-operation, scoped assignment, and mobile scenarios.

Phase 09H maps employee create/edit cases and examination scope evidence to
the existing checklist. The remaining write and revocation matrix stays
open. Phase 10 has not started.

Phase 09I verifies payroll confidentiality, financial writes and selected live
revocations, plus teacher attendance revocation and examination write scope.
Further financial workflow and role assertions remain tracked in the Phase 09
acceptance checklist. Phase 10 has not started.

Phase 09J adds salary draft editing and verifies that effective-dated salary
assignments preserve finalized payroll, that separate approval uses distinct
actors, and that salary setup and teacher marks permissions take effect when
revoked. It also covers selected leave, staff calendar and retention workflows
at 390 px. Phase 09 remains **INCOMPLETE** pending the outstanding cases in the
[Phase 09J checklist](PHASE_09_ACCEPTANCE_REPORT.md#phase-09j-checklist-reconciliation).
Phase 10 has not started.

Phase 09K adds evidence for the five-role HR and financial authorization
matrix and the 390 px teaching assignment and overtime workflows. Phase 09
remains **INCOMPLETE** while effective-dated leave policy revisions are open.
The [Phase 09K report](PHASE_09_ACCEPTANCE_REPORT.md#phase-09k) lists the exact
passing and remaining IDs. Phase 10 has not started.

Phase 09L adds effective-dated leave policy versions and ledger provenance.
See the [Phase 09L acceptance report](PHASE_09_ACCEPTANCE_REPORT.md#phase-09l)
for checklist closure and the remaining sensitive salary activation approval
scope. Phase 10 has not started.

Phase 09M closes the supplemental salary structure approval requirement.
The [Phase 09M report](PHASE_09_ACCEPTANCE_REPORT.md#phase-09m-supplemental-acceptance)
records the explicit decisions, secure activation, legacy migration, and
verification. The fixed checklist remains 211 of 211 passing. Phase 09 is
**COMPLETE**. Phase 10 has not started.

Phase 10 implements the timetable workspace, scheduling and publication
APIs, dated changes, attendance snapshots and examination warnings. The
[Phase 10 timetable guide](TIMETABLE_MANAGEMENT.md) lists current coverage and
open scope. Phase 11 has not started.

Phase 10B extends timetable scheduling and reporting. Operational deployment
remains blocked pending verification of a restorable encrypted institutional
backup. The [acceptance report](PHASE_10_ACCEPTANCE_REPORT.md) records isolated
results and open acceptance coverage. Phase 11 has not started.


## Phase 10C verification status

Functional acceptance remains incomplete, operational backup verification is blocked on operator configuration, and operational migrations are pending approval after a verified restore. See the [Phase 10 acceptance report](PHASE_10_ACCEPTANCE_REPORT.md).

Phase 10D retains the operational migration gate and tracks outstanding
functional evidence in the [Phase 10 acceptance report](PHASE_10_ACCEPTANCE_REPORT.md).

Phase 10E evidence and open scheduling, reporting, authorization, and
deployment items are maintained in the [Phase 10 acceptance report](PHASE_10_ACCEPTANCE_REPORT.md#phase-10e).

Phase 10F adds future roster successors and cross-version relocations.
Functional and operational closeout remain tracked independently in the
[Phase 10 acceptance report](PHASE_10_ACCEPTANCE_REPORT.md#phase-10f).
