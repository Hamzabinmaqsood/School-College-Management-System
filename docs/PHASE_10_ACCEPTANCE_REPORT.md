# Phase 10 acceptance report

## Phase 10B scope and safety

Operational PostgreSQL responded at `127.0.0.1:5433`. Read-only inspection
identified the existing school database and application owner, HR through
0011, attendance through 0003, and no timetable migrations applied.
The pending plan includes HR 0012–0013, attendance 0004, and timetable
0001–0005. No operational schema or data was changed.

The workspace had no configured institutional encrypted backup destination
or recovery key. An AES-256 encrypted `pg_dump` and actual restore into a
separate disposable database passed with synthetic data. That exercise did
not copy operational records or verify an operational backup. See the
[backup and restore gate](DEPLOYMENT.md#phase-10b-backup-and-restore-gate).
`scripts/run-migrations.sh` now checks for missing migration files and
prints the plan before applying it.

## Implemented and isolated verification

| Area | Implementation and verification scope |
| --- | --- |
| Optional groups | One optional group per session, section and subject. Enrollment membership is explicit and becomes fixed after submission. Tests covered overlapping-member rejection, disjoint parallel lessons, and a grouped attendance roster. |
| Preferences and workload | Weighted preferred or non-preferred times affect ranking and warnings. Hard unavailability remains blocking. Effective hard and soft policies use daily, weekly and consecutive period limits plus clock-minute rest. Tests covered soft preference and workload warnings and hard weekly rejection. |
| Cross-date changes | Moves within a published version keep the original occurrence and create a dated destination. Tests covered closures, examination and HR leave conflicts, and refusal after finalized attendance. The original register stayed intact. Completeness counts only the destination. |
| Reports | Fourteen named reports reuse the effective schedule or version and allocation data. The report workspace supports scope, date ranges, pagination, CSV and browser printing. The relocation report deduplicates source and destination. |
| Authorization | Backend tests exercised five account profiles for review and publication, a valid authorized control, an unchanged denied state and an audit event. Broader role-by-operation coverage remains open. |
| License | Isolated signed-license coverage verified expired write denial, published reads and authorized export. |
| Concurrency | The existing PostgreSQL publication race passed. An exhaustive race matrix for group membership, workloads and dated exceptions remains open. |

## Known limits

A published option group has fixed membership and does not support multiple
groups for the same subject in a section. Rescheduling is limited to the same
published version. Hard workload policies have no override flow. The complete
five-role by operation matrix and live revocation for every grant remain open.
All report variants and HR and examination edge cases still need individual
acceptance, including exam-teacher duties and cross-version relocation.

Phase 11 has not started.

## Reproduction

Run each command from the repository root in WSL. The launcher creates a
private PostgreSQL cluster and uses disposable users and signing keys.

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend frontend/tests/browser/phase09/seed.py
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
SMS_PHASE10=desktop SMS_PHASE10B=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE10=mobile SMS_PHASE10B=1 SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
```

A runnable isolated workflow is available without applying any operational
migration. The operational backup and migration gate is unchanged.

## Browser and restore evidence

- Desktop Chromium and mobile Chromium at 390×844 each passed the extended
  workflow with optional-group membership, soft preference validation,
  workload configuration, separate review, live approval revocation and
  restoration, grouped attendance, cross-date relocation, and report CSV.
  The browser reports are `/tmp/sms10b-release-desktop/results.json` and
  `/tmp/sms10b-release-mobile/results.json`.
- Before the final browser runs, the report selector and Angular multiple
  selection locators were corrected to match the actual rendered controls.
- The synthetic encrypted restore log is `/tmp/sms10b-backup-probe.log`.
  Read-only operational inventory and plan are `/tmp/sms10b-operational.log`
  and `/tmp/sms10b-operational-plan.log`.
- The dated conflict regression confirmed that a later draft cannot double-book
  a teacher or room already reserved by a moved lesson. Its test output is
  `/tmp/sms10b-dated-conflict.log`.
- Angular lint, TypeScript, 36 unit tests and the 950.92 kB production build
  passed. See `/tmp/sms10b-angular-final.log`.

| Final regression | Result | Evidence |
| --- | --- | --- |
| PostgreSQL | 72 passed and 9 subtests passed | `/tmp/sms10b-verified-pg.log` |
| SQLite | 60 passed, 12 skipped and 9 subtests passed. Django and migration checks passed. | `/tmp/sms10b-verified-sqlite.log` |
| Existing desktop/mobile baseline | 5 passed and 3 configured skips | `/tmp/sms10b-full-final/results.json` |
| Extended desktop and mobile workflow | 1 passed per viewport | `/tmp/sms10b-release-desktop/results.json` and `/tmp/sms10b-release-mobile/results.json` |

**Phase 10 functional verification · INCOMPLETE.**

**Operational deployment · BLOCKED.**

**Overall Phase 10 · INCOMPLETE.**

## Phase 10C

Operational read-only inventory confirmed `school_management_db` on
`127.0.0.1:5433`. HR 0012–0013, attendance 0004, and timetable 0001–0005
remain pending. No operational changes were applied. A successful synthetic
run of `scripts/verify-encrypted-backup.sh --verify` encrypted a PostgreSQL
archive and restored it to a private cluster. The checksum, counts and
migration records matched. The operational `--status` check stopped at the
missing approved backup directory. The institution also needs a provisioned
recovery key and PostgreSQL service, restored institutional readback, and
explicit migration authorization.

The original 41 criteria are recorded in the
[Phase 10 checklist](../frontend/tests/browser/phase09/timetable-checklist.json).
The Phase 09 checklist was preserved.

### Report verification matrix

The following tests each exercised an isolated PostgreSQL fixture for an
authorized read at license expiry, a CSV response, pagination metadata,
and a denied read from a signed-in account with only approval scope.
The primary data assertions are listed below. These checks use a
session-scoped range and do not imply complete printable output or edge-case
coverage for every report.

| Report | Independently checked result |
| --- | --- |
| Class timetable | Five dated rows and the scheduled subject |
| Section timetable | Five dated rows in the expected section |
| Teacher weekly | Five dated rows and the expected teacher |
| Teacher daily | The first original date inside the requested range |
| Room utilization | 180 occupied minutes |
| Teacher workload | Expected teacher count and 120 minutes for the first teacher |
| Subject allocation | One weekly lesson allocated |
| Unassigned required periods | Empty for the fully allocated fixture |
| Scheduling conflicts | Empty for the conflict-free fixture |
| Substitute teacher register | One row with the original teacher |
| Canceled lesson register | One canceled occurrence |
| Rescheduled lesson register | One relocation with the destination date |
| Timetable revision history | One published revision |
| Attendance completeness | Three expected occurrences after cancellation and relocation |

Backend evidence is `backend/tests/test_timetables.py::test_all_report_routes_reconcile_and_export_after_license_expiry`.
PostgreSQL and SQLite ran all fourteen subtests.

### Remaining acceptance

Existing role evidence covers separate approval, publication and a signed-in
reviewer's approval revocation. The full five-role by operation matrix and
other live grant revocations still need evidence. Published group membership
remains frozen, and successor membership after transfers or admission needs
a reviewed design and verification. Cross-version moves still require source
and destination version handling. The hard workload policy still blocks
violations and has no override. Broader race coverage and HR and examination
edge cases remain open.

**Functional acceptance · INCOMPLETE. Operational backup · BLOCKED.
Operational migrations · PENDING. Overall Phase 10 · INCOMPLETE.**
Phase 11 has not started.

### Phase 10C regression evidence

| Check | Result | WSL evidence |
| --- | --- | --- |
| PostgreSQL regression on an isolated database | 75 passed, 23 subtests passed | `/tmp/sms10c-pg-verified.log` |
| SQLite regression | 61 passed, 14 skipped, 23 subtests passed | `/tmp/sms10c-sqlite-verified.log` |
| Publication concurrency | Three PostgreSQL race cases passed for a shared teacher, room, and section | `/tmp/sms10c-races.log` |
| Targeted reports | 1 passed, 14 subtests passed | `/tmp/sms10c-report.log` |
| Angular unit tests, lint, type check and production build | 36 unit tests passed; initial bundle 951.24 kB | `/tmp/sms10c-angular-final.log` |
| Extended timetable workflow and print layout | 1 desktop and 1 mobile Chromium test passed | `/tmp/sms10c-desktop/results.json`, `/tmp/sms10c-mobile/results.json` |
| Existing browser regression suite | 5 passed, 3 skipped | `/tmp/sms10c-baseline/results.json` |
| Encrypted synthetic backup and isolated restore | Passed; counts, migration records and checksum matched | `/tmp/sms10c-synthetic-final.log` |
| Operational identity and migration plan | Read-only checks succeeded; migrations pending | `/tmp/sms10c-operational-identity.log`, `/tmp/sms10c-operational-plan.log` |

The [41-criterion checklist](../frontend/tests/browser/phase09/timetable-checklist.json)
records 29 PASS, 11 NOT_TESTED, and 1 BLOCKED. The browser entries for
full desktop and mobile acceptance remain open because the passing extended
workflow covers a subset of the requested scenarios. Browser logs and
artifacts under `/tmp` are local to the verification environment.

### Reproduce isolated verification

Run from the repository root in WSL with the project's Node environment active.

```bash
.venv/bin/python -m pytest -q
SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh --list
(cd frontend && npm test && npm run lint && npm run typecheck && npm run build)
SMS_PHASE10=desktop SMS_PHASE10B=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE10=mobile SMS_PHASE10B=1 bash frontend/tests/browser/phase09/run.sh
bash frontend/tests/browser/phase09/run.sh
```

The PostgreSQL regression and browser runner provision their own private cluster.
Run the browser invocations sequentially when using the default ports.
The earlier browser suite skips three mobile copies of authorization cases
that it exercises on desktop.

The class and teacher layouts were checked using Chromium print media.
Browser-native pagination and PDF output remain unverified. The report print
button prints the loaded report page; verify multi-page reports before
treating the browser output as a complete report.

### Scheduling and integration evidence

- Teacher, room, and section publication contention each left one published
  version, one approved contender, one effective lesson, and one publication
  audit record. Races involving optional groups, workload changes,
  substitutions, relocations, and revision creation remain open.
- An approved Phase 09 leave fixture blocked a move to the leave day.
  Soft preferences produced warnings and hard workload limits blocked
  excess work in separate cases. Employment lifecycle and overtime cases
  still require coverage.
- A real Phase 08 `ExamSchedule` fixture blocked a time-overlapping move.
  Exam room, rescheduling, substitution, and revision combinations still
  require coverage.
- A finalized attendance snapshot was checked unchanged after a blocked
  move. The report fixture counted three expected occurrences after
  cancellation and relocation, and a separate test checked an optional
  group's snapshotted roster. Transfer, admission, withdrawal, and
  cross-version scenarios remain open.

## Phase 10D

The previous open criteria were TT-04 breaks, TT-06 class timetable creation,
TT-09 curriculum, TT-10 teacher eligibility, TT-19 publication protection,
TT-23 daily leave, TT-31 reports, TT-32 dynamic RBAC, TT-37 desktop,
TT-38 mobile and TT-40 earlier-module regression. TT-34 is the operational
migration criterion. The checklist preserves all 41 IDs and records the
test and interaction needed for each remaining row.

A read-only operational check verified the database, role, server port,
and eight pending migrations. The backup status check stopped at the missing
approved backup directory. No operational migration or restore was run.

Backend tests directly verify break, curriculum and eligibility controls,
published-entry protection, and daily approved leave without a recurring
schedule rewrite. CSV export recognizes UTF-8, neutralizes formula-like
content, and denies a view-only account while allowing its ordinary report
read. Full coverage requires additional browser and report cases.

Chromium-generated class and teacher PDFs initially included a navigation
link and transient notices. The print layout now hides those elements.
The all-report browser loop records a distinct date-range, displayed result
count, and CSV download assertion for each report.

The original workload disposition remains in force. Room-capacity override,
cross-version relocations, full five-role operation coverage and the
remaining revocations remain unresolved.

### Phase 10D deployment and reproduction

Default development startup remains `bash scripts/start-dev.sh`. See the
preceding test-command block for isolated regression commands. Import an
executed Phase 10D Playwright result with:

```bash
node frontend/tests/browser/phase09/update-timetable-evidence.mjs /path/to/results.json
```

The importer requires explicit assertion evidence for every report in the
identified test and viewport. It preserves the criterion's acceptance state.
Verify the operational backup gate with
`bash scripts/verify-encrypted-backup.sh --status`. Follow the deployment
runbook before any operational migration.

### Phase 10D browser report results

Each row passed the class of assertions recorded in the importer. These are
browser fixture counts for the selected two-day window. The larger backend
fixture above provides separate reconciliation. A zero count is an empty-state check.

| Report | Desktop rows | 390px rows | Download |
| --- | ---: | ---: | --- |
| class | 2 | 2 | `class.csv` |
| section | 2 | 2 | `section.csv` |
| teacher-weekly | 2 | 2 | `teacher-weekly.csv` |
| teacher-daily | 2 | 2 | `teacher-daily.csv` |
| rooms | 1 | 1 | `rooms.csv` |
| workload | 1 | 1 | `workload.csv` |
| allocations | 0 | 0 | `allocations.csv` |
| unassigned | 0 | 0 | `unassigned.csv` |
| conflicts | 0 | 0 | `conflicts.csv` |
| substitutions | 0 | 0 | `substitutions.csv` |
| cancellations | 0 | 0 | `cancellations.csv` |
| reschedules | 1 | 1 | `reschedules.csv` |
| revisions | 1 | 1 | `revisions.csv` |
| attendance | 1 | 1 | `attendance.csv` |

Real PDF output for the class and own-scope teacher schedules was one page on
each viewport. Text extraction verified institution, subject and revision,
and confirmed that the attendance link and status messages were absent.
Evidence is in `/tmp/sms10d-pdf-final.log` and the two Playwright output
directories under `/tmp/sms10d-*-final`.

A PostgreSQL race between two relocations to the same destination committed
one exception, delivered one effective lesson, and emitted one audit event.
The other request returned a section conflict. Group acceptance confirmed
that the published roster and attendance snapshot survived a withdrawal;
the existing session, section and subject uniqueness constraint rejected
creation of a successor group. Successor roster support remains open.

### Phase 10D fresh regression evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Isolated PostgreSQL | 79 passed, 29 subtests | `/tmp/sms10d-pg-final.log` |
| SQLite | 64 passed, 15 skipped, 29 subtests | `/tmp/sms10d-sqlite-final.log` |
| Angular | 36 unit tests passed, lint and TypeScript passed | `/tmp/sms10d-angular-final.log` |
| Production build | 951.29 kB initial, 202.56 kB estimated transfer | `/tmp/sms10d-angular-final.log` |
| Timetable workflow | One passing desktop and one passing 390px run | `/tmp/sms10d-desktop-final/results.json`, `/tmp/sms10d-mobile-final/results.json` |
| Earlier browser suite | 5 passed, 3 skipped | `/tmp/sms10d-baseline/results.json` |
| PostgreSQL races and leave integration | 5 passed, 3 subtests | `/tmp/sms10d-races.log` |
| Group history | Published roster protected, successor rejected | `/tmp/sms10d-group-final.log` |
| Read-only operational status | Identity confirmed, eight migrations pending | `/tmp/sms10d-operational.log` |

Phase 10D retains 29 PASS, 11 open functional rows with partial evidence
where applicable, and 1 blocked operational row. Functional acceptance and
overall Phase 10 remain incomplete. Operational backup is blocked and
operational migrations are pending. Phase 11 has not started.

Live report-read and export revocation separately passed on desktop and
390px Chromium. Removing export access denied CSV with HTTP 403 while
retaining the report read. Removing the read grant denied the report with
HTTP 403 and withheld the timetable page on reload. The evidence artifacts
are `/tmp/sms10d-revoke-desktop/results.json` and
`/tmp/sms10d-revoke-mobile/results.json`.

## Phase 10E

The phase began with 29 passing criteria, 11 open functional criteria,
and TT-34 blocked. Previous evidence and original IDs remain in the
[machine-readable checklist](../frontend/tests/browser/phase09/timetable-checklist.json).

| Criterion | Previous coverage | Phase 10E closure requirement |
| --- | --- | --- |
| TT-04 Break intervals | Backend denied an invalid placement | Save and rediscover a real break, reject overlapping configuration and lesson placement, verify no write, and schedule an adjacent teaching period in both viewports |
| TT-06 Class timetable creation | Single section-scoped lesson published | Create two lessons from Angular, verify weekly allocation and persisted entries, then review, publish and read as administrator and teacher |
| TT-09 Curriculum validation | Backend rejected a subject outside the curriculum | Verify scoped Angular choices and session, inactive subject, optional-group and enrollment cases |
| TT-10 Teacher eligibility | Backend denied an unassigned teacher | Verify choices and effective assignment, contract, and leave boundaries through UI and API |
| TT-19 Published timetable protection | Published PATCH and DELETE were denied | Verify immutable UI, successor lifecycle, stale and concurrent writes, audit and existing attendance |
| TT-23 Daily leave | Approved leave flagged the affected date | Verify live date-specific substitution and untouched recurrence, plus remaining leave and employment cases |
| TT-31 Reports and exports | All reports and CSV exercised on both viewports | Close historical and report-specific scopes, reconciliation, and complete PDF variants |
| TT-32 Dynamic RBAC | Approval, report read and export revocation | Finish applicable operations and remaining revocations across all five profiles |
| TT-37 Desktop browser | Core workflow passed | Execute all required outstanding scenarios at desktop width |
| TT-38 Mobile browser | Core workflow passed | Execute all required scenarios at 390px and verify interactions and layout |
| TT-40 Earlier-module regression | Previous backend and baseline browser passes | Run fresh isolated suites and verify earlier-module compatibility and historical access |

Phase 10E fixed the timetable form checkbox binding. The previous binding
submitted a teaching period even when the checkbox appeared unchecked.
Non-teaching intervals now display a break label in the configuration and
lesson selector. The operational probe remained read-only and confirmed
the same eight planned migrations. The backup check stopped at the missing
approved destination.

### Phase 10E regressions and deployment evidence

| Check | Fresh result | Evidence |
| --- | --- | --- |
| Isolated PostgreSQL | 79 passed, 29 subtests | `/tmp/sms10e-pg.log` |
| SQLite | 64 passed, 15 skipped, 29 subtests | `/tmp/sms10e-sqlite.log` |
| Angular | 36 unit tests passed; lint and TypeScript passed | `/tmp/sms10e-angular-final.log` |
| Production build | 951.61 kB initial, 202.63 kB estimated transfer | `/tmp/sms10e-angular-final.log` |
| Earlier-module baseline browser | 5 passed, 3 mobile duplicates skipped | `/tmp/sms10e-baseline/results.json` |
| Earlier-module finance browser | 5 passed | `/tmp/sms10e-finance/results.json` |
| Operational identity and migration plan | Read-only; eight pending migrations | `/tmp/sms10e-operational.log` |
| Backup readiness | Approved destination missing | `/tmp/sms10e-backup.log` |

Django system checks, migration consistency, and Ruff passed. There were no
new migrations. The timetable runner used the existing private PostgreSQL
and disposable signed fixture environment. The operational database was
queried using read-only transactions.

### Phase 10E criteria closed

- **TT-04.** Both viewports saved and rediscovered a non-teaching interval,
  rejected an overlapping configuration and a lesson placement, checked that
  the rejected placement stored no lesson, accepted adjacent teaching times,
  and allowed the same break hours in a separate shift.
- **TT-06.** Both viewports created two scheduled lessons, reconciled the
  weekly allocation and stored entries, published after independent review,
  and showed the published lessons in class and own-teacher views.
- **TT-40.** Fresh isolated backend, Angular and earlier-module browser
  regressions passed. Finance exercised all five existing profile fixtures.

Core browser evidence is in `/tmp/sms10e-core-desktop/results.json` and
`/tmp/sms10e-core-mobile/results.json`. Each passed one focused test. The
focused test deliberately ends after the publication and attendance handoff.

### Phase 10E full timetable browser evidence

Both full Playwright runs passed two tests each. They verified day-specific
approved leave and substitution, as well as a successor timetable that could
be edited and published without changing the original occurrence and notes.
All 14 report reads and CSV responses passed with class, session and date
filters. Four one-page Chromium PDFs passed checks for branding, revision
and both lessons, with attendance links absent. Report-read, approval and
CSV-export live revocation passed again on both viewports.

Artifacts are in `/tmp/sms10e-complete-desktop/results.json`,
`/tmp/sms10e-complete-mobile/results.json`, and `/tmp/sms10e-print.log`.
The full runs used the freshly built production bundle with the isolated
runner's PostgreSQL, fixture, Django and proxy identity checks.

The original matrix now records **32 PASS, 8 open functional criteria,
1 operationally BLOCKED, and 0 FAIL**. TT-09, TT-10, TT-19, TT-23, TT-31,
TT-32, TT-37 and TT-38 remain open. Work remains on the all-case role matrix,
historical group successors, cross-version relocation, room-capacity
override, broader concurrency and complete report printing. Functional
acceptance and overall Phase 10 are incomplete. The operational backup
is blocked, migrations are pending, and Phase 11 has not started.

## Phase 10F

| Open criterion | Targeted work | Remaining closure evidence |
| --- | --- | --- |
| TT-09 Curriculum validation | Existing server-side subject and roster validation applies to successors | Scoped Angular subject options and remaining curriculum cases |
| TT-10 Teacher eligibility | Moves are checked against the effective destination date | Scoped Angular teacher options and complete employment boundary matrix |
| TT-19 Published timetable protection | Future roster revision, original occurrence preservation, cross-version contention | Broader publication, transfer, attendance and audit cases |
| TT-23 Daily leave | Destination move reuses effective employment, leave and availability checks | Complete HR and examination edge-case matrix |
| TT-31 Reports and exports | Source and destination revisions in schedule data; complete report print flow | Room PDF, remaining scoped report cases, and full report authorization |
| TT-32 Dynamic RBAC | Successor creation uses timetable management and student-view grants | Full five-role operation and revocation matrix |
| TT-37 Desktop acceptance | Core timetable and historical scheduling workflow | Remaining capacity, report, historical and security scenarios |
| TT-38 Mobile acceptance | Same workflow at 390px | Remaining capacity, report, historical and security scenarios |

The original group remains frozen. A successor is tied to a future draft of
the same plan, inherits eligible enrollment links and replaces the roster
on matching draft entries. Publication controls the switch. Retained
historical entries and persisted attendance continue to refer to their
original roster. This phase adds timetable migrations 0006 and 0007.

A dated move resolves the effective published revision for the destination
and preserves the original entry and occurrence. The move applies the
destination's roster and validates the target slot. Existing attendance at
either source or destination blocks the move. The normal timetable
transaction serializes concurrent moves and publications.

The operational read-only check confirmed ten pending migrations, including
the two new timetable migrations. The backup gate stopped at the missing
approved destination. No operational migration or restore ran.

### Phase 10F regression evidence

| Check | Fresh result | Artifact |
| --- | --- | --- |
| Isolated PostgreSQL | 80 passed, 29 subtests | `/tmp/sms10f-pg-release.log` |
| SQLite | 65 passed, 15 skipped, 29 subtests | `/tmp/sms10f-sqlite-release.log` |
| Angular | 36 passed; lint and TypeScript passed | `/tmp/sms10f-angular-release.log` |
| Production build | 954.55 kB initial, 203.33 kB estimated transfer | `/tmp/sms10f-angular-release.log` |
| Earlier browser baseline | 5 passed, 3 skips | `/tmp/sms10f-baseline/results.json` |
| Operational identity and plan | Read-only, ten pending migrations | `/tmp/sms10f-operational.log` |
| Operational backup status | Approved destination missing | `/tmp/sms10f-backup.log` |

The PostgreSQL contention test submits two moves from the earlier revision
to one destination in the later revision. It checks for one HTTP 201,
one HTTP 409, one saved exception, one effective destination lesson and
one audit event. The roster regression excludes an enrollment ending
on the effective boundary, then verifies original and successor group
identity on either side of the boundary and the existing attendance snapshot.

The final desktop and 390px suites each passed two tests. Both created
and reviewed a successor roster, moved an occurrence to the next published
revision, verified all fourteen report reads and CSV downloads, and
rechecked report and CSV grant revocation. Chromium generated a five-page
historical class report on each viewport. Text extraction found the
institution, selected scope and both revisions with interactive controls
absent. The artifact directories are `/tmp/sms10f-desktop-verified` and
`/tmp/sms10f-mobile-verified`. PDF extraction is in `/tmp/sms10f-pdf.log`.

No additional criterion met its complete closeout conditions. The original
matrix remains 32 passed, eight open, and TT-34 blocked. Functional and
overall Phase 10 acceptance remain incomplete. Operational backup is blocked,
operational migrations are pending, and Phase 11 has not started.

## Phase 10G focused eligibility verification

The Angular lesson editor blocks stale subject, teacher and group selections,
requires an eligible optional teaching group before saving, and clears stale
plan/version state while a newly selected plan is loading. The plan picker,
version selector and lesson actions are disabled during plan loading so a
lesson-options request cannot combine a new plan with the prior plan's version.
The first fresh desktop rerun exposed this race; the browser received HTTP 400
for the mismatched plan/version. After the fix, the complete extended desktop
and mobile workflows passed.

The optional-subject browser assertion was also corrected to validate the
standard JSON error envelope and the exact message in `details`:
“Choose an explicit teaching group for an optional subject.” Django validation
was unchanged, and rejected entries were verified not to persist.

| Check | Fresh result |
| --- | --- |
| Backend suite | 66 passed, 15 skipped, 30 subtests passed |
| Isolated PostgreSQL regression | 81 passed, 30 subtests passed |
| Angular unit tests | 38 passed |
| Angular lint and typecheck | Passed |
| Angular production build | Passed in both isolated browser workflows |
| Browser test and fixture syntax | Passed |
| Desktop Phase 10 browser run | 2 passed; `/tmp/sms-phase09-evidence.5hs22d` |
| Mobile Phase 10 browser run at 390px | 2 passed; `/tmp/sms-phase09-evidence.KlMeWz` |

Both browser runs used the isolated temporary PostgreSQL cluster and the
extended eligibility scenarios. Linux Node.js 24.22.3 was used through WSL
`nvm`; the user-installed `libasound2t64` resolved Chromium startup.

TT-09 passes: curriculum choices are scoped to the selected class/session,
inactive and foreign subjects are excluded, invalid subjects are rejected
without writes, and optional subjects require an explicit eligible group.
TT-10 passes: assigned eligible teachers are selectable, unassigned and
out-of-scope teachers are excluded, and assignment/effective-date and
employment eligibility are covered by backend regressions.

The acceptance matrix now records **34 PASS, 6 open functional criteria,
1 operationally BLOCKED, and 0 FAIL**. TT-19, TT-23, TT-31, TT-32, TT-37 and
TT-38 remain open. TT-34 remains blocked by operational backup and migration
requirements. No operational database or school records were changed, no
operational migrations were run, and Phase 11 has not started.

### Isolated demo database and repository state

The persistent demo cluster is ready at
`~/.local/share/school-management-demo-phase10g`, with database
`sms_phase10g_demo`, role `sms_phase10g_demo_app`, and a private Unix socket on
port 55480. It has no TCP listener; migrations are current and disposable
Browser Academy fixtures are present. `scripts/start-demo.sh --check` verified
that Django connects to this database through the private socket. Demo setup
uses a generated test-only signing key and does not read production signing
keys or `backend/.env`.

At the start of this work, the Git worktree had no usable commit baseline:
`HEAD` pointed to an unborn `master`, `.git/index` and Git objects were absent,
there were no remotes, and all project files were untracked. No repository
reset or deletion was performed.

## Phase 10H final verification

The original 41-criterion checklist now records **40 PASS, 0 OPEN, 1
BLOCKED, and 0 FAIL**. TT-09 and TT-10 remain PASS with the Phase 10G
curriculum and teacher-eligibility evidence. TT-19, TT-23, TT-31, TT-32,
TT-37, and TT-38 are PASS after the isolated PostgreSQL and full browser
workflows described in their checklist entries. TT-34 remains blocked pending
a verified operational backup and explicit authorization for operational
migrations. This final count supersedes older interim totals earlier in this
report.

### Fresh regressions

| Verification | Result |
| --- | --- |
| Isolated PostgreSQL backend suite | 83 passed; 35 subtests passed |
| Angular unit tests | 38 passed |
| Angular lint, TypeScript, and production build | Passed |
| Desktop Chromium, 1440x900 | 3 passed |
| Mobile Chromium, 390x844 | 3 passed; no horizontal overflow |
| Demo database identity check | Passed against `sms_phase10g_demo` on its private socket |

Latest browser evidence is
`/mnt/c/Users/Malik/.copilot/session-state/9b1d9563-331f-4d75-8e0c-bf9dd5d22c78/files/phase10h-evidence/desktop/results.json` and
`/mnt/c/Users/Malik/.copilot/session-state/9b1d9563-331f-4d75-8e0c-bf9dd5d22c78/files/phase10h-evidence/mobile/results.json`. The final browser reruns include
the five-role UI and operation matrix, protected room reporting, and live
grant revocation. TT-19/23/31/32 evidence is cross-referenced in
`frontend/tests/browser/phase09/timetable-checklist.json`. No acceptance
failure remains in these runs.

### Demo manual verification

The persistent disposable demo database remains ready. `scripts/start-demo.sh
--check` confirmed the backend connects to the dedicated `sms_phase10g_demo`
database through the private Unix socket; the demo is pinned away from the
operational database. The application was previously started and its API and
authorized demo login were verified. Chromium startup is resolved by the
manually installed WSL `libasound2t64`; browser runs use Linux Node.js 24.22.3
activated through nvm.

From Ubuntu WSL, start the demo and use the exact URL below:

```sh
cd ~/school-management-system
bash scripts/start-demo.sh --check
SMS_DEMO_DJANGO_PORT=8041 SMS_DEMO_ANGULAR_PORT=4241 bash scripts/start-demo.sh
```

Open `http://127.0.0.1:4241/login` and sign in as `fixture-admin`. Retrieve
the generated password locally from
`~/.local/share/school-management-demo-phase10g/fixtures.json`; do not place
it in a command, chat, screenshot, or log. Stop the application with Ctrl+C.
Only disposable Browser Academy data is intended for manual testing.

### Git protection and operational boundary

The repository remains on an unborn `master` because it has no commit; there
are no remotes. Before preparing the baseline, there were zero tracked files
and no Git index. The workspace alone cannot establish why its history was
absent. The audit found
the application `.env` and generated database/cache artifacts excluded by
`.gitignore`; `.env.example` is the only environment template included in the
baseline. The audited baseline is staged with 335 source, configuration, and
documentation files. No credentials, signing keys, databases, backups,
virtual environments, dependencies, or generated build artifacts are staged.
No initial commit was created; approval is still required before committing.

Operational deployment remains blocked. No operational migrations or school
record changes were made, no production signing keys were used, and Phase 11
has not started.
