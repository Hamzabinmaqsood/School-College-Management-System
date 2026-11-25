# Attendance management

## Historical and reporting rules

Attendance uses existing enrollments. An enrollment is eligible from its start
date up to, but excluding, its recorded end date. On a same-day section transfer,
the receiving enrollment owns new attendance that day. A register snapshots the
historical enrollment and placement when created. An existing daily snapshot
reserves that student/date, even after a retroactive transfer. Other class or
section registers cannot create a second daily mark for the student that day.

Daily registers are identified by academic session, class, section and date.
Period registers also include subject and normalized period identifier. A missing
section is the unsectioned group. A session-specific subject assignment overrides
the class default for that subject. There is no timetable dependency.

Daily and period statistics use separate denominators. Finalized marked records
are the basis of percentages. Present counts as attended. Late and excused follow
the rules snapshotted on the register. Unmarked and draft entries are reported
separately. Finalizing a register with unmarked students requires explicit
acknowledgement. A percentage is unavailable when its denominator is zero.

## Workflow and storage

Open Attendance, choose the historical session, class, section and date, and
load the roster. Subject-period registers also require a stable period code such
as P1. Teachers select from their assignments. Save draft marks before
finalizing. Explicitly acknowledge unmarked students. Corrections retain the
previous mark, actor, reason and time.

The attendance app owns settings, calendar exceptions, teaching assignments,
registers, roster slots, corrections, leave requests and leave decisions.
PostgreSQL validates the session, date and mode on each mark against its register.
Calendar changes apply when opening new registers. A working-day override requires
its own permission and a reason.

The role matrix supports separate list, detail, mark, finalize, correct, history,
export, print, leave, settings, calendar and assignment permissions. Teachers
need both action permissions and the relevant exact assignment. An unsectioned
assignment applies to unsectioned enrollment. A daily assignment has no subject.
The protected administrator receives the new permissions on migration.

Leave requests must fit one placement interval. Pending and approved requests
for the same student and session cannot overlap. Approval annotates registers.
An authorized correction can explicitly apply approved leave as an excused mark.
Audits omit private remarks and reasons.

## API and reports

Routes are relative to /api/v1/.

| Route | Methods |
| --- | --- |
| attendance/ | GET registers, POST draft |
| attendance/{id}/ | GET snapshot, PATCH marks |
| attendance/{id}/{save,finalize,correct}/ | POST |
| attendance/{roster,groups,lookups,history}/ | GET |
| attendance/{summary,reports,report-filters,export,print}/ | GET |
| attendance/student/{id}/ | GET |
| attendance/leaves/ and attendance/leaves/{id}/ | GET, POST collection |
| attendance/leaves/{sessions,classes,choices}/ | GET |
| attendance/leaves/{id}/{approve,reject,cancel}/ | POST |
| attendance/settings/ | GET, PATCH |
| attendance/holidays/ and attendance/assignments/ | GET, POST |
| attendance/holidays/{id}/ and attendance/assignments/{id}/ | GET, PATCH |

Draft updates and corrections send the last read register version. A 409
indicates a stale version or a conflicting state. Reports accept date range,
mode, session, class, section, subject, student, and percentage threshold.
CSV supports Urdu through UTF-8 with BOM, escapes formula prefixes, and omits
remarks and private leave reasons. Printable HTML uses local fonts. A browser
with print-to-PDF can save a PDF offline.

The dashboard uses the institution's local day and configured primary mode.
Daily statistics can detect eligible students missing a register. Period
completeness covers captured periods because the timetable is a later phase.

## Licensing and checks

The signed attendance feature is required for register, leave, calendar,
settings and assignment mutations. Authorized reads, exports, printing and
existing backups remain available after expiration.

From Ubuntu at the repository root, run:

    .venv/bin/python backend/manage.py check
    .venv/bin/python backend/manage.py makemigrations --check --dry-run
    .venv/bin/python -m pytest -q
    .venv/bin/ruff check backend
    cd frontend
    npm run typecheck
    npm run lint
    npm test
    npm run build

For PostgreSQL tests, set DB_HOST, DB_PORT, DB_USER and DB_NAME to an isolated
database before calling pytest with --ds=config.settings.development. Use test-only
signing keys.

**Open attendance** on a published timetable lesson prefills its existing
group, date, subject and period. A matching new register stores a timetable
snapshot. Existing registers and manual periods keep their original records
and use the same attendance permissions.

Optional-group registers are limited to the group's eligible enrollments
when a published lesson matches. The register stores the optional group,
lesson, version and original date in its snapshot. A timetable relocation
cannot move an occurrence with an existing attendance register.
