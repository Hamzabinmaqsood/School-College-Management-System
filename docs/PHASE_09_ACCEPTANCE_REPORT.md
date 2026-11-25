# Phase 09C HR and payroll acceptance

**Phase 09 status: INCOMPLETE.** The desktop administrator assignment lifecycle
passed. The complete teacher-side Angular acceptance and the full role and
calendar matrices still require verification.

Chrome ran against a loopback-only proxy serving the production Angular bundle
and an isolated Django/PostgreSQL database. Desktop Chrome started at 1440 px
and reported an effective 1418 px content viewport. The mobile iframe reported
390 px. Fixture users, licensing keys, payments and attendance belonged solely
to the isolated acceptance database. No host clock changes were made.

PASS refers to the explicitly listed assertion. NOT TESTED identifies remaining
acceptance scope even where narrower automated or browser assertions passed.

| Requirement | Implementation | Backend verification | Angular unit verification | Chrome evidence | Result |
| --- | --- | --- | --- | --- | --- |
| Administrator assignment lifecycle | `hr/people.py`, `attendance/serializers.py`, employee profile | Scoped history test verifies create, extend, deactivate, and history access | General HR form suite | Actual login, profile, session/class/section/subject selection, upcoming/current/expired states, date edits, extension, confirm deactivation, five history rows. Account linking used the authenticated API | PASS |
| Assignment authorization boundaries | `attendance/access.py` | Controlled clock verifies day before start, start, end and day after end, including overlap and revocation | No teacher-boundary test | Administrator UI shows statuses. Teacher-side UI boundary matrix was not run | NOT TESTED |
| Student attendance and exams | `attendance/register_api.py`, `examinations/marks_api.py` | Full regression includes attendance teacher scope and revocation, exam teaching scope, mark validation, publication and concurrency | General suites ran | Assigned teacher navigation, direct writes at every date boundary, and full submit/approve/publish distinction not exercised in Chrome | NOT TESTED |
| Department schedules | `hr/api.py`, `hr/schedule.py` | Template copy, overnight clock and existing contract snapshot verified | General HR form suite | Desktop Chrome API configured a schedule and copied break/shift values to a contract | PASS |
| Additional schedule cases | `hr/api.py` | Snapshot after template edit verified | No dedicated schedule UI scenario | Second contract after update, invalid ranges and permission matrix not all exercised in browser | NOT TESTED |
| Contract leave override and ledger | `hr/accrual.py`, `hr/leave_balance.py` | Override, annual accrual, repeat posting, cancellation reversal, adjustment replay, carry cap and expiry verified | No dedicated ledger unit test | Chrome API previewed and posted 18.5 days, retried as a no-op, and approved one day leaving 17.5 | PASS |
| Leave policy edge cases | Same as above | Full acceptance matrix not covered by current tests | No dedicated test | Zero overrides, concurrent accrual, multiple types and contract expiration not exercised end to end | NOT TESTED |
| Staff calendar | `hr/calendar.py`, `hr-page.html` | Overnight schedule, clock times, paid hours and tolerances verified | General HR form suite | Angular employee/month form returned a recorded day at desktop and 390 px | PASS |
| Calendar matrix | Same as above | Full status and visibility matrix not covered | No dedicated calendar unit test | Department filtering, month changes, corrections, errors and all statuses not exercised in both viewports | NOT TESTED |
| Overtime and payroll | `hr/overtime.py`, `hr/payroll.py`, `hr/reports.py` | Pending exclusion, approved inclusion, deductions, idempotent posting and concurrency verified | Payroll preview and payment form tests | Desktop Chrome API verified one overtime earning, finalized payroll, paid 450 then 850, retried the first payment, reconciled zero payable, rejected finalized recalculation, and opened printable payslip HTML and reports | PASS |
| Document retention | `hr/people.py`, employee profile | Private download, retention date, hold, release, history, and archive verified | No dedicated retention unit test | Due queue, extension and denial not exercised in Chrome | NOT TESTED |
| RBAC | HR view permissions and shared permission services | Regression covers authorization, private documents, and scoped history denial | Auth suite ran | Restricted account read its allowed staff calendar and received HTTP 403 for payroll. Full five-role matrix remains open | NOT TESTED |
| Offline subscription | Shared license gates used by HR and payroll | Regression covers activation, renewal, replay, expiration, export, backup and unauthorized features | Auth and connectivity suites ran | Expired license blocked HR and payroll writes. Authorized payroll reads and CSV export succeeded. Renewal restored an HR write. Backup and printable payslip under expiration were not checked in Chrome | NOT TESTED |
| Regression and build | Django and Angular projects | System checks, migration consistency and Ruff passed. PostgreSQL 51 passed, SQLite 44 passed and 7 skipped. Each reported 6 passing subtests | 34 passed. TypeScript, ESLint and production build passed | Application tested using the built bundle | PASS |

## Issues fixed

The employee profile recorded assignment changes in the audit log but had no
assignment history control. Added a paginated history endpoint limited to the
selected employee's assignment and institution. Access requires both teacher
view and assignment management permissions. The profile now lists who made the
change, when it occurred, and the previous and new dates when available. The
regression test checks successful retrieval, an unknown assignment, and denial
for the linked teacher without management permission.

## Browser evidence

| Scenario | Chrome marker | Supporting assertion |
| --- | --- | --- |
| Administrator assignment lifecycle | `passed-1418` | Login and assignment history returned HTTP 200, with five history rows rendered |
| Staff calendar | `passed-390` | Angular form returned recorded staff attendance at the mobile width |
| Schedule, leave and overtime | `passed-1418` | Contract copied a 30-minute break, leave balance reconciled to 17.5, payroll preview included one overtime line |
| Finalized payroll | `passed-1418` | Payment post/retry/post returned 201/200/201. Recalculation returned 409. Payslip and reports returned 200 |
| Restricted user | `passed-1418` | Calendar HTTP 200, payroll list HTTP 403 |
| Expired license and renewal | `passed-1418` for each run | Expired writes returned 403, payroll export 200, renewal 201, subsequent accrual write 200 |

## Remaining acceptance

Run both attendance and exam Angular workflows as a separately authenticated
teacher. Finish the role-by-role grant matrix, full calendar interaction and
status matrix, and remaining leave and document retention browser scenarios.

## Phase 09D follow-up

Phase 09 remains **INCOMPLETE**. Phase 09C evidence above is historical.
Phase 09D used fresh PostgreSQL regression and browser databases, a separate
loopback browser server, isolated accounts, and disposable signing keys.

### Execution checklist and new browser evidence

| ID | Role and viewport | Angular route and backend | Expected and observed | Result |
| --- | --- | --- | --- | --- |
| D01 | Teacher, 1418 and 390 px | `/attendance`, `/attendance/history` and attendance group, roster, save and finalize APIs | Signed in through Angular, selected the assigned class/section/subject group and period, loaded the roster, marked present, saved the draft, finalized it and found the register in history. Roster, save and finalize returned 200 in both runs using separate periods | PASS |
| D02 | Teacher, 1418 px | `/examinations/marks`, marks save and submit APIs | Opened the scoped assessment, entered 59, saved the draft, reopened the roster and verified 59.00, submitted through the confirmation dialog and saw submitted status. Save and submit returned 200 | PASS |
| D03 | Teacher, 1418 px | `/hr/payroll` and protected APIs | Angular redirected to Access denied. Direct payroll, salary structure, salary assignment, payroll export, documents and marks verification requests returned 403 | PASS |
| D04 | Administrator, 1418 and 390 px | `/hr/attendance/calendar`, HR calendar endpoint | Selected an employee and month, checked present, absent, late, leave, holiday, nonworking, excused and unrecorded rows, checked overnight clock times, changed month, and opened department totals | PASS |
| D05 | Administrator, 1418 px | `/hr/leave-types` and `/hr/leaves`, accrual and decision APIs | Created a 12-day paid policy, previewed and posted it through Angular, repeated posting, approved one day and reconciled 11 days, then cancelled it and saw 12 days restored with a reversal | PASS |
| D06 | Administrator, 1418 px | Employee profile and retention queue, HR document APIs | Opened the due queue and confirmed the due fixture was visible and the archived scan was excluded. Uploaded a generated PNG through the form, extended the review date, placed and released a hold, checked the archive action was absent while on hold, archived via confirmation and reviewed audit history | PASS |

The register and exam tests used the existing scoped query and authorization
regressions as supporting coverage. The browser test did not substitute those
regressions for the missing unauthorized-date and unrelated-group scenarios.
The first leave request selected a fixture nonworking day and received HTTP 400.
Selecting an eligible day returned HTTP 201. No production defect was established
by that run.

### Outstanding acceptance

| Requirement | Implementation and expected outcome | Remaining browser verification | Result |
| --- | --- | --- | --- |
| Teacher attendance scope | Attendance group and roster endpoints expose effective teaching assignments | Student profile attendance, unrelated groups and direct unauthorized writes across future, expired and disabled assignment states | NOT TESTED |
| Teacher exam scope | Marks workbench and marks APIs apply assignment and workflow grants | Unrelated class/subject, date-boundary writes, and approval/publication denials | NOT TESTED |
| Calendar corrections | HR attendance correction retains previous values in the audit record | Corrections, history review, unauthorized correction denial, timezone boundary | NOT TESTED |
| Leave edge cases | Leave policy, contract overrides and accrual ledger under HR | Browser carry cap and expiry, zero entitlement, proration, contract expiration, concurrent execution and unauthorized adjustment | NOT TESTED |
| Document retention | HR settings, due queue and private document permissions | Per-type policy setup, opening a document from the due queue, and direct unauthorized download of a specific document | NOT TESTED |
| Mobile interaction matrix | HR, attendance and marks Angular pages | All listed workflows except staff calendar and student attendance at 390 px | NOT TESTED |

### Fresh regression results

- PostgreSQL 51 passed with 6 passing subtests.
- SQLite 44 passed, 7 skipped, with 6 passing subtests.
- Angular 34 passed. TypeScript, ESLint and the production build passed.
- Django system checks, migration consistency, and Ruff passed.

No application code or migrations changed in Phase 09D. Sanitized Chrome
assertion markers are in WSL `/tmp/sms09d-evidence`, outside the project and
customer package.

### Five-role browser and API matrix

All five fixture accounts authenticated using the Angular sign-in form. Each
account then attempted the direct Angular payroll route and requested the five
listed APIs from its authenticated browser session. Status expectations reflect
the explicit fixture grants. Teacher salary and export denials are also listed in D03.

| Capability tested | Institution administrator | HR officer | Teacher | Payroll officer | Restricted employee |
| --- | --- | --- | --- | --- | --- |
| Employee list API | 200 | 200 | 403 | 403 | 403 |
| Employee document list API | 200 | 200 | 403 | 403 | 403 |
| Staff attendance list API | 200 | 200 | 403 | 403 | 403 |
| Employee leave list API | 200 | 200 | 403 | 403 | 403 |
| Payroll list API | 200 | 403 | 403 | 200 | 403 |
| Direct Angular payroll route | Allowed | Denied | Denied | Allowed | Denied |

**Result for the checks above: PASS. Full five-role matrix: NOT TESTED.**
Navigation visibility, per-operation Angular routes, explicit revocation and
sensitive-data field checks were not completed for every account. The remaining
operations include employee profiles, individual documents, teaching assignments,
leave and overtime approvals, salary structures and assignments, payroll
preview/generation/approval, salary payment posting, payslip access, HR reports,
and payroll exports. The teacher-only denials in D03 and individual administrator
scenarios do not establish results for the other roles.

## Phase 09E closeout

**Phase 09 remains INCOMPLETE.** Earlier sections are historical. The
[machine-readable checklist](../frontend/tests/browser/phase09/checklist.json)
expands the outstanding workflows and role checks into separately tracked
assertions. The Playwright suite under `frontend/tests/browser/phase09` uses a
private PostgreSQL cluster, disposable accounts and signing key, and loopback
Django and Angular servers.

| Scope | Phase 09E evidence | Result |
| --- | --- | --- |
| Teacher attendance | Angular showed the effective assigned group and omitted unrelated, future, expired and inactive groups. The assigned roster returned 200 at the combined inclusive start and end boundary. Direct roster access outside scope and current register creation with future, expired or inactive assignments returned 403. | PASS for listed assertions |
| Student profile and revocation | Assigned profile attendance tab and teacher grant revocation still require acceptance. | NOT TESTED |
| Teacher examinations | The Phase 09D scoped marks save and submit remain verified. Unrelated groups, date boundaries, approval/publication, and revocation were not rerun in Phase 09E. | NOT TESTED |
| Five-role matrix | Phase 09D list and route checks remain verified. Phase 09E additionally confirmed the HR fixture sees the employee profile without Salary history and the employee JSON excludes salary, gross, net, payroll and salary history. The full action and revocation matrix remains open. | NOT TESTED for full matrix |
| Staff calendar | Playwright required a correction reason, then confirmed a correction and displayed prior and revised values and the reason at 1440 and 390 px. Backend regression asserts missing reason and unauthorized history access are rejected. Timezone and working-day override boundaries remain open. | PASS for listed assertions |
| Leave policies | Two simultaneous PostgreSQL accrual requests returned 200, posted one credit in total, and both returned 12 days. This is backend-only verification. Policy changes, zero/prorated entitlement, contract expiry and browser edge cases remain open. | PASS for concurrency |
| Document retention | Authorized operator selected a due row, downloaded the exact private scan and opened the employee profile at 1440 and 390 px. Restricted exact-download request returned HTTP 403 with JSON. Per-type policy setup and policy-derived review date still require browser verification. | PASS for listed assertions |
| Mobile | Playwright operated correction controls and history and the due-document actions at 390 px. Other previously outstanding mobile pages remain open. | NOT TESTED for full matrix |

Application changes were limited to an attendance correction-history endpoint
and view, plus permission-gated profile and download links in the due queue.
No migration was required. The new leave concurrency regression uses the existing
PostgreSQL transaction-test harness.

Fresh regression results after the final application changes were PostgreSQL
52 passed, SQLite 44 passed with 8 skipped, and Angular 34 passed. Both backend
runs reported six passing subtests. Django checks, migration consistency, Ruff,
TypeScript, ESLint and the production build passed.

Browser JSON reports are stored outside the workspace under WSL `/tmp`; each
Playwright run prints its evidence directory. The browser remains loopback-only.

The final Playwright run reported **5 passed and 3 skipped**. The skips avoid
duplicating server-side authorization or serialization assertions in the mobile
project. Evidence is in `/tmp/sms09e-evidence-release/results.json` and
`/tmp/sms09e-evidence-release/http-statuses.log`. Earlier full harness runs
reported HTTP 500 after repeated requests to the isolated Django development
server. Disabling persistent database connections for that server resolved the
combined run. The operational configuration was unchanged.

The checklist records 17 passing assertions and 194 not tested. Its rows include
individual role/action combinations, so its totals are separate from the number
of Playwright tests.

## Phase 09F

### Port diagnosis

On the Phase 09F host, the listeners on 8000 and 4200 belonged to the same
existing Django and Angular stack. Both readiness checks reported PostgreSQL
connected. The default startup correctly reported both conflicts and exited
before launching either child. An unrelated loopback HTTP listener was
reported without being classified as the school application. Invalid port
values and a shared Django/Angular port were rejected.

An alternate stack used Django 8012 and Angular 4212. Direct Django health
and Angular-proxied readiness returned HTTP 200. Only the alternate stack
started for verification was stopped.

### Acceptance classification

The [machine-readable checklist](../frontend/tests/browser/phase09/checklist.json)
retains all 211 IDs, identifies overlapping assertions, assigns the required
verification type, and records the remaining action for each open assertion.
No assertion was removed or classified as inapplicable. A passing role-specific
assertion does not close the remaining role-by-action combinations.

### Evidence conventions

Browser flows used an isolated PostgreSQL cluster and disposable signing
keys. The three conditional mobile skips avoid repeating desktop
authorization and serialization checks. They do not represent missing
dependencies or fixture failures. Desktop and 390 px still run the
interactive correction and retention workflows.

### New backend checks

- The staff calendar test fixed the clock at a UTC month boundary and
  confirmed the institution's next-day local date. It also confirmed a
  working-day exception changed an otherwise nonworking day to unrecorded,
  without counting it as absent or duplicating dates.
- Leave accrual tests verified a zero entitlement, joining-date proration,
  and reversion from the expired contract override to the policy rate on a
  subsequent accrual. Carry-forward and expiration remained covered by the
  full backend regression.
- The isolated acceptance runner also rejects collisions with the operational
  Angular port before PostgreSQL provisioning.

Fresh results were PostgreSQL 54 passed, SQLite 46 passed and 8 skipped,
and Angular 34 passed. Each backend run reported six passing subtests.
Django checks, migration consistency, Ruff, TypeScript, ESLint, and the
production build passed. No application migration was required.

### Browser results and closure decision

| Area | Phase 09F evidence |
| --- | --- |
| Teacher attendance | Opened the assigned student's Angular profile and Attendance tab, selected Subject period, and verified one eligible session and one present mark. Existing scope denials reran successfully. Permission revocation remains open. |
| Teacher examinations | Opened the Angular assessment roster and confirmed the verification control was absent. The teacher received 403 from direct verification, approval and publication requests. The approval and publication checks exercised the permission gate before result lookup. Unrelated groups, assignment validity and revocation remain open. |
| Role matrix | The HR profile confidentiality assertion reran. A restricted account received 403 for the exact private document, an existing attendance correction endpoint, and leave adjustment. The complete role-by-operation matrix remains open. |
| Retention | At 1440 and 390 px, saved a 30-day per-type policy, uploaded a contract file and verified its displayed review date. Also reran authorized queue navigation and download. |
| Calendar and leave | Correction and correction history reran at both widths. Backend tests cover timezone, working-day overrides, zero entitlement, proration and contract expiry. These backend checks do not substitute for unverified UI workflow assertions. |

The final Playwright run reported **5 passed, 3 skipped**. Results and sanitized
request statuses are in `/tmp/sms09f-evidence-verified/results.json` and
`/tmp/sms09f-evidence-verified/http-statuses.log`.

| PASS | FAIL | BLOCKED | NOT TESTED | NOT APPLICABLE |
| ---: | ---: | ---: | ---: | ---: |
| 32 | 0 | 0 | 179 | 0 |

All 211 IDs remain. The 179 open assertions comprise 167 browser automation,
9 backend integration, and 3 frontend unit classifications. The checklist provides
each outstanding ID, reason, and verification action. No production feature
or migration changed. **Phase 09 remains INCOMPLETE.** Phase 10 was not started.

## Phase 09G

The new Playwright matrix derived expected access from the fixture users'
effective grants. All five accounts signed in through Angular. Each account
exercised nine HR reads and six direct Angular routes. The permitted HR pages
also checked visible and hidden Human Resources navigation links against the
same grants. The matrix covers employee list and detail, attendance list and
calendar, leave list, salary structures, overtime, payroll, and download of an
existing private document. This verifies the read subset of the matrix.

The authorized control changed a custom HR role through the existing permissions
API. Without signing out, the HR browser then received 403 for the employee
list and was denied the direct route. After navigation refreshed the user's
grants, the Employees link disappeared. The API error exposed no employee rows.
Other action and revocation combinations remain open in the checklist.

The launcher proves the PostgreSQL server's private data directory and socket
connection, then compares the unique fixture institution ID through the Angular
proxy before starting Playwright. The first revocation harness revision reused
the browser's cookie jar for the administrator control request. Separate API
request contexts corrected this test issue. No application code or database
migration changed. The default application ports had no listener when this
execution began. No operational process or database was stopped or modified.

### New verification

| Run | Fresh result |
| --- | --- |
| Isolated PostgreSQL regression | 54 passed and 6 passing subtests |
| SQLite | 46 passed, 8 skipped, and 6 passing subtests |
| Angular unit tests | 34 passed |
| Playwright five-role read matrix | 5 passed |
| Playwright desktop and 390 px workflows | 5 passed and 3 intentional mobile skips |
| Quality and build | Django checks, migration consistency, Ruff, ESLint, TypeScript and production build passed |

New evidence is in `/tmp/sms09g-matrix-verified/` and
`/tmp/sms09g-browser-final/`. Each directory has a JSON report and
sanitized request statuses. The [checklist](../frontend/tests/browser/phase09/checklist.json)
retains all 211 IDs and gives a grouped execution procedure for each open item.

The focused examination rerun passed. The teacher received 403 for approval
and publication of an existing result; the administrator control received 200
for both operations on the same fixture result. This replaces the prior
placeholder-ID evidence without increasing the number of passed examination
IDs. The request evidence is in `/tmp/sms09g-result-controls/http-statuses.log`.
The evidence updater validates the recorded test and supporting request
statuses before attaching them to the existing checklist IDs.

| PASS | FAIL | BLOCKED | NOT TESTED | NOT APPLICABLE |
| ---: | ---: | ---: | ---: | ---: |
| 33 | 0 | 0 | 178 | 0 |

Teacher attendance, staff correction history, and retention reran with the
existing workflows. The run did not add new leave edge cases or complete
teacher exam date/scope cases. The exact open IDs and closure procedures are
in the checklist. **Phase 09 remains INCOMPLETE.** Phase 10 was not started.

## Phase 09H

The checklist is broader than a list of HTTP responses. Phase 09G's 45 reads
and 30 direct route attempts overlapped earlier read coverage and supplied
only part of many role-action requirements. They did not exercise write forms,
persistence, or effective permission changes for those actions. The one new
ID in that phase recorded the completed employee-list revocation workflow.

### Executed security coverage

The five fixture roles exercised employee creation and editing. Expectations
came from effective grants. Authorized cases submitted the Angular form and
confirmed the saved value through an administrator read. Denied cases first
verified the initial data, submitted the same valid payload in the restricted
session, checked the permission-specific 403, checked persisted state stayed
unchanged, and confirmed an administrator could execute that payload. Each role
had its own edit target and creation code. The HR officer edited successfully
and then received a permission-specific 403 after both staff-view and edit
grants were revoked in the existing session. The administrator confirmed the
previous edit was preserved. Browser and control requests used separate sessions.

The existing read matrix reran. This does not close all confidentiality
requirements for individual payroll entries, salary payments, payslips, or
exports. The remaining write roles and actions, including employment status,
user linking, assignment management, documents, attendance, leave, overtime
and payroll, are identified in the checklist.

### Evidence handling

The checklist retains all 211 IDs. The security evidence updater maps passing
Playwright outcomes to specific IDs and rejects missing or duplicate evidence.
Recorded evidence includes the test, role, endpoint, route, viewport,
verified behavior and artifact. Historical evidence remains in place.

The first denied-write test looked for the permission reason in the generic
message. The API carries that reason in the response details, so the test now
checks both 403 and the specific reason. Unrelated examination fixtures were
also separated from the result publication fixture. This preserves the result's
original calculation inputs when the authorized publication control runs.
These were test harness fixes. No application code or migration changed.

### Regression results

- PostgreSQL 54 passed with six passing subtests.
- SQLite 46 passed, eight skipped, with six passing subtests.
- Angular 34 passed. Django system checks, migration consistency, Ruff,
  ESLint, TypeScript and the production build passed.
- Playwright five-role matrix 5 passed. Evidence:
  `/tmp/sms09h-matrix-verified/results.json`.

The final desktop and 390 px workflow suite reported **5 passed and 3
intentional mobile skips**. Teacher attendance and student-profile coverage
reran with the current fixtures. For examinations, the administrator read
each existing nonassigned submission while the teacher received 404 for
the unrelated class, subject and section. The same teacher received 404 for
future, expired and inactive assignment reads, and access returned after
restoring the valid dates. An expired **write** is still unverified.
Approval and publication again used the valid separate result with the
administrator control. Evidence is in
`/tmp/sms09h-verified/results.json` and
`/tmp/sms09h-verified/http-statuses.log`.

| PASS | FAIL | BLOCKED | NOT TESTED | NOT APPLICABLE |
| ---: | ---: | ---: | ---: | ---: |
| 48 | 0 | 0 | 163 | 0 |

Phase 09H added ten employee create/edit IDs and five examination scope IDs.
The exact IDs and evidence are recorded in the checklist. **Phase 09 remains
INCOMPLETE.** Phase 10 was not started.

<details>
<summary>Exact remaining checklist IDs</summary>

- **teacher attendance scope** · `E-ATT-11`
- **teacher examination scope** · `E-EXAM-01`, `E-EXAM-06`, `E-EXAM-12`
- **staff calendar** · `E-CAL-04`, `E-CAL-06`, `E-CAL-07`
- **leave ledger** · `E-LEAVE-01`, `E-LEAVE-02`, `E-LEAVE-03`, `E-LEAVE-06`, `E-LEAVE-08`, `E-LEAVE-11`, `E-LEAVE-12`
- **retention lifecycle** · `E-DOC-04`, `E-DOC-06`, `E-DOC-07`, `E-DOC-08`, `E-DOC-09`, `E-DOC-10`
- **390px interactions** · `E-MOB-01`, `E-MOB-02`, `E-MOB-03`, `E-MOB-05`, `E-MOB-06`, `E-MOB-07`, `E-MOB-08`, `E-MOB-09`, `E-MOB-10`
- **five-role action matrix** · `E-RBAC-EMPLOYEES-ADMINISTRATOR-01`, `E-RBAC-EMPLOYEES-ADMINISTRATOR-04`, `E-RBAC-EMPLOYEES-HR_OFFICER-04`, `E-RBAC-EMPLOYEES-TEACHER-01`, `E-RBAC-EMPLOYEES-TEACHER-04`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-01`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-04`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-04`, `E-RBAC-DOCUMENTS-ADMINISTRATOR-01`, `E-RBAC-DOCUMENTS-ADMINISTRATOR-02`, `E-RBAC-DOCUMENTS-HR_OFFICER-01`, `E-RBAC-DOCUMENTS-HR_OFFICER-02`, `E-RBAC-DOCUMENTS-TEACHER-01`, `E-RBAC-DOCUMENTS-TEACHER-02`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-01`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-02`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-01`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-02`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-01`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-02`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-03`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-04`, `E-RBAC-ATTENDANCE-HR_OFFICER-01`, `E-RBAC-ATTENDANCE-HR_OFFICER-02`, `E-RBAC-ATTENDANCE-HR_OFFICER-03`, `E-RBAC-ATTENDANCE-HR_OFFICER-04`, `E-RBAC-ATTENDANCE-TEACHER-01`, `E-RBAC-ATTENDANCE-TEACHER-02`, `E-RBAC-ATTENDANCE-TEACHER-03`, `E-RBAC-ATTENDANCE-TEACHER-04`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-01`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-02`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-03`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-04`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-01`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-02`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-03`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-04`, `E-RBAC-LEAVES-ADMINISTRATOR-01`, `E-RBAC-LEAVES-ADMINISTRATOR-02`, `E-RBAC-LEAVES-ADMINISTRATOR-03`, `E-RBAC-LEAVES-ADMINISTRATOR-04`, `E-RBAC-LEAVES-ADMINISTRATOR-05`, `E-RBAC-LEAVES-HR_OFFICER-01`, `E-RBAC-LEAVES-HR_OFFICER-02`, `E-RBAC-LEAVES-HR_OFFICER-03`, `E-RBAC-LEAVES-HR_OFFICER-04`, `E-RBAC-LEAVES-HR_OFFICER-05`, `E-RBAC-LEAVES-TEACHER-01`, `E-RBAC-LEAVES-TEACHER-02`, `E-RBAC-LEAVES-TEACHER-03`, `E-RBAC-LEAVES-TEACHER-04`, `E-RBAC-LEAVES-TEACHER-05`, `E-RBAC-LEAVES-PAYROLL_OFFICER-01`, `E-RBAC-LEAVES-PAYROLL_OFFICER-02`, `E-RBAC-LEAVES-PAYROLL_OFFICER-03`, `E-RBAC-LEAVES-PAYROLL_OFFICER-04`, `E-RBAC-LEAVES-PAYROLL_OFFICER-05`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-02`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-03`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-04`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-05`, `E-RBAC-OVERTIME-ADMINISTRATOR-01`, `E-RBAC-OVERTIME-ADMINISTRATOR-02`, `E-RBAC-OVERTIME-ADMINISTRATOR-03`, `E-RBAC-OVERTIME-ADMINISTRATOR-04`, `E-RBAC-OVERTIME-HR_OFFICER-01`, `E-RBAC-OVERTIME-HR_OFFICER-02`, `E-RBAC-OVERTIME-HR_OFFICER-03`, `E-RBAC-OVERTIME-HR_OFFICER-04`, `E-RBAC-OVERTIME-TEACHER-01`, `E-RBAC-OVERTIME-TEACHER-02`, `E-RBAC-OVERTIME-TEACHER-03`, `E-RBAC-OVERTIME-TEACHER-04`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-01`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-02`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-03`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-04`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-01`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-02`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-03`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-04`, `E-RBAC-PAYROLL-ADMINISTRATOR-01`, `E-RBAC-PAYROLL-ADMINISTRATOR-02`, `E-RBAC-PAYROLL-ADMINISTRATOR-03`, `E-RBAC-PAYROLL-ADMINISTRATOR-04`, `E-RBAC-PAYROLL-ADMINISTRATOR-05`, `E-RBAC-PAYROLL-ADMINISTRATOR-06`, `E-RBAC-PAYROLL-ADMINISTRATOR-07`, `E-RBAC-PAYROLL-ADMINISTRATOR-08`, `E-RBAC-PAYROLL-ADMINISTRATOR-09`, `E-RBAC-PAYROLL-ADMINISTRATOR-10`, `E-RBAC-PAYROLL-HR_OFFICER-01`, `E-RBAC-PAYROLL-HR_OFFICER-02`, `E-RBAC-PAYROLL-HR_OFFICER-03`, `E-RBAC-PAYROLL-HR_OFFICER-04`, `E-RBAC-PAYROLL-HR_OFFICER-05`, `E-RBAC-PAYROLL-HR_OFFICER-06`, `E-RBAC-PAYROLL-HR_OFFICER-07`, `E-RBAC-PAYROLL-HR_OFFICER-08`, `E-RBAC-PAYROLL-HR_OFFICER-09`, `E-RBAC-PAYROLL-HR_OFFICER-10`, `E-RBAC-PAYROLL-TEACHER-01`, `E-RBAC-PAYROLL-TEACHER-02`, `E-RBAC-PAYROLL-TEACHER-03`, `E-RBAC-PAYROLL-TEACHER-04`, `E-RBAC-PAYROLL-TEACHER-05`, `E-RBAC-PAYROLL-TEACHER-06`, `E-RBAC-PAYROLL-TEACHER-07`, `E-RBAC-PAYROLL-TEACHER-08`, `E-RBAC-PAYROLL-TEACHER-09`, `E-RBAC-PAYROLL-TEACHER-10`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-01`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-02`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-03`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-04`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-05`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-06`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-07`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-08`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-09`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-10`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-01`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-02`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-03`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-04`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-05`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-06`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-07`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-08`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-09`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-10`

</details>

## Phase 09I

The isolated finance suite uses real fixture salary assignments, periods,
salary advances, finalized runs, payments and payslips. Each actor has a
separate period for writes. Expectations come from the fixture's effective
permissions. The browser authenticates as the tested role and a separate
request context performs administrator controls.

### Financial security

- The read matrix checks salary structures and assignments, payroll period,
  run detail and embedded entries, advances, payment history and detail,
  employee salary history, payslips, and payroll reports and exports.
  When access is forbidden it checks a 403 response without results, entries,
  or the fixture compensation amount. The administrator reads each fixture
  resource successfully.
- Finance cases cover assignment creation, preview and generation, submission,
  review, approval, finalization, payment, reversal and adjustment. Denied
  writes check the authorization reason and compare persisted state before
  the same request succeeds as administrator. Payment tests verify idempotent
  retries, Decimal balances, reversal, adjustment, and rejection of draft
  recalculation after finalization. Audit reads confirm generation, approval,
  finalization, payment and reversal events.
- In the existing payroll officer session, revocation blocks payroll detail,
  payment posting, printable payslips, and payroll CSV export. The balance
  is preserved and a fresh Angular navigation denies the payroll route.
  Creation and revision of salary structures and assignment changes remain
  outside these new tests. The test periods allow the same approver; separate
  approver policy is not established by this suite.
- Angular approval, review, finalization, payment, printable payslip and export
  controls were exercised where the fixture grant permits them. This does not
  claim that every UI action was tested for every denied role.

### Security-related UI fix

After payroll export revocation, the backend denied the request, but Angular
still offered the payroll export link to users with the general HR export
grant. Financial report links now require both export grants and the report's
read grant. The regression checks link removal for payroll and continued
visibility for authorized employee exports. The backend gate was unchanged.

### Teacher write evidence

An existing teacher created an attendance draft. Removing the draft creation
grant in the same session prevented the next valid draft and retained attendance
history access. Angular showed the roster read-only and omitted the draft action.
Restoring the grant permitted the write again.

The teacher saved a marks draft at the combined inclusive start/end boundary.
Future, expired and inactive assignments and unrelated class, section and
subject writes were denied with unchanged marks. An administrator successfully
submitted the same save payload in each scoped denial. Revoking update and
submit permissions returned 403 with unchanged marks and revision. Angular
removed the affected controls after refresh. After restoration the teacher
submitted the marks via Angular at desktop and at 390 px. The other examination
revocations, including verifier, approver and publisher grants, remain open.

### Fresh regression

PostgreSQL 54 passed, SQLite 46 passed and 8 skipped, and Angular 35 passed.
Both backend runs reported six passing subtests. Django checks, migration
consistency, Ruff, TypeScript, ESLint, and the production build passed.
No database migration was required.

| Browser run | Result | Evidence |
| --- | --- | --- |
| Five-role payroll desktop | 5 passed | `/tmp/sms09i-desktop-release/results.json` |
| Payroll at 390 px | 1 passed | `/tmp/sms09i-mobile-release/results.json` |
| Teacher writes and revocation desktop | 1 passed | `/tmp/sms09i-teacher-final/results.json` |
| Teacher writes and revocation at 390 px | 1 passed | `/tmp/sms09i-teacher-release/results.json` |

| PASS | FAIL | BLOCKED | NOT TESTED | NOT APPLICABLE |
| ---: | ---: | ---: | ---: | ---: |
| 74 | 0 | 0 | 137 | 0 |

The evidence importer only promotes assertions associated with the executed
role or viewport and the corresponding recorded operation. The acceptance
status remains **INCOMPLETE**. Phase 10 was not started.

<details>
<summary>Newly passing and exact remaining checklist IDs</summary>

**Newly passing:** `E-ATT-11`, `E-EXAM-06`, `E-MOB-03`, `E-MOB-08`, `E-MOB-09`, `E-RBAC-PAYROLL-ADMINISTRATOR-01`, `E-RBAC-PAYROLL-ADMINISTRATOR-02`, `E-RBAC-PAYROLL-ADMINISTRATOR-03`, `E-RBAC-PAYROLL-ADMINISTRATOR-04`, `E-RBAC-PAYROLL-ADMINISTRATOR-05`, `E-RBAC-PAYROLL-ADMINISTRATOR-06`, `E-RBAC-PAYROLL-ADMINISTRATOR-07`, `E-RBAC-PAYROLL-ADMINISTRATOR-08`, `E-RBAC-PAYROLL-HR_OFFICER-02`, `E-RBAC-PAYROLL-TEACHER-02`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-01`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-02`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-03`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-04`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-05`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-06`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-07`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-08`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-09`, `E-RBAC-PAYROLL-PAYROLL_OFFICER-10`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-02`

- **teacher examination scope** · `E-EXAM-01`, `E-EXAM-12`
- **staff calendar** · `E-CAL-04`, `E-CAL-06`, `E-CAL-07`
- **leave ledger** · `E-LEAVE-01`, `E-LEAVE-02`, `E-LEAVE-03`, `E-LEAVE-06`, `E-LEAVE-08`, `E-LEAVE-11`, `E-LEAVE-12`
- **retention lifecycle** · `E-DOC-04`, `E-DOC-06`, `E-DOC-07`, `E-DOC-08`, `E-DOC-09`, `E-DOC-10`
- **390px interactions** · `E-MOB-01`, `E-MOB-02`, `E-MOB-05`, `E-MOB-06`, `E-MOB-07`, `E-MOB-10`
- **five-role action matrix** · `E-RBAC-EMPLOYEES-ADMINISTRATOR-01`, `E-RBAC-EMPLOYEES-ADMINISTRATOR-04`, `E-RBAC-EMPLOYEES-HR_OFFICER-04`, `E-RBAC-EMPLOYEES-TEACHER-01`, `E-RBAC-EMPLOYEES-TEACHER-04`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-01`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-04`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-04`, `E-RBAC-DOCUMENTS-ADMINISTRATOR-01`, `E-RBAC-DOCUMENTS-ADMINISTRATOR-02`, `E-RBAC-DOCUMENTS-HR_OFFICER-01`, `E-RBAC-DOCUMENTS-HR_OFFICER-02`, `E-RBAC-DOCUMENTS-TEACHER-01`, `E-RBAC-DOCUMENTS-TEACHER-02`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-01`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-02`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-01`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-02`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-01`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-02`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-03`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-04`, `E-RBAC-ATTENDANCE-HR_OFFICER-01`, `E-RBAC-ATTENDANCE-HR_OFFICER-02`, `E-RBAC-ATTENDANCE-HR_OFFICER-03`, `E-RBAC-ATTENDANCE-HR_OFFICER-04`, `E-RBAC-ATTENDANCE-TEACHER-01`, `E-RBAC-ATTENDANCE-TEACHER-02`, `E-RBAC-ATTENDANCE-TEACHER-03`, `E-RBAC-ATTENDANCE-TEACHER-04`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-01`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-02`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-03`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-04`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-01`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-02`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-03`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-04`, `E-RBAC-LEAVES-ADMINISTRATOR-01`, `E-RBAC-LEAVES-ADMINISTRATOR-02`, `E-RBAC-LEAVES-ADMINISTRATOR-03`, `E-RBAC-LEAVES-ADMINISTRATOR-04`, `E-RBAC-LEAVES-ADMINISTRATOR-05`, `E-RBAC-LEAVES-HR_OFFICER-01`, `E-RBAC-LEAVES-HR_OFFICER-02`, `E-RBAC-LEAVES-HR_OFFICER-03`, `E-RBAC-LEAVES-HR_OFFICER-04`, `E-RBAC-LEAVES-HR_OFFICER-05`, `E-RBAC-LEAVES-TEACHER-01`, `E-RBAC-LEAVES-TEACHER-02`, `E-RBAC-LEAVES-TEACHER-03`, `E-RBAC-LEAVES-TEACHER-04`, `E-RBAC-LEAVES-TEACHER-05`, `E-RBAC-LEAVES-PAYROLL_OFFICER-01`, `E-RBAC-LEAVES-PAYROLL_OFFICER-02`, `E-RBAC-LEAVES-PAYROLL_OFFICER-03`, `E-RBAC-LEAVES-PAYROLL_OFFICER-04`, `E-RBAC-LEAVES-PAYROLL_OFFICER-05`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-02`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-03`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-04`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-05`, `E-RBAC-OVERTIME-ADMINISTRATOR-01`, `E-RBAC-OVERTIME-ADMINISTRATOR-02`, `E-RBAC-OVERTIME-ADMINISTRATOR-03`, `E-RBAC-OVERTIME-ADMINISTRATOR-04`, `E-RBAC-OVERTIME-HR_OFFICER-01`, `E-RBAC-OVERTIME-HR_OFFICER-02`, `E-RBAC-OVERTIME-HR_OFFICER-03`, `E-RBAC-OVERTIME-HR_OFFICER-04`, `E-RBAC-OVERTIME-TEACHER-01`, `E-RBAC-OVERTIME-TEACHER-02`, `E-RBAC-OVERTIME-TEACHER-03`, `E-RBAC-OVERTIME-TEACHER-04`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-01`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-02`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-03`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-04`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-01`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-02`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-03`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-04`, `E-RBAC-PAYROLL-ADMINISTRATOR-09`, `E-RBAC-PAYROLL-ADMINISTRATOR-10`, `E-RBAC-PAYROLL-HR_OFFICER-01`, `E-RBAC-PAYROLL-HR_OFFICER-03`, `E-RBAC-PAYROLL-HR_OFFICER-04`, `E-RBAC-PAYROLL-HR_OFFICER-05`, `E-RBAC-PAYROLL-HR_OFFICER-06`, `E-RBAC-PAYROLL-HR_OFFICER-07`, `E-RBAC-PAYROLL-HR_OFFICER-08`, `E-RBAC-PAYROLL-HR_OFFICER-09`, `E-RBAC-PAYROLL-HR_OFFICER-10`, `E-RBAC-PAYROLL-TEACHER-01`, `E-RBAC-PAYROLL-TEACHER-03`, `E-RBAC-PAYROLL-TEACHER-04`, `E-RBAC-PAYROLL-TEACHER-05`, `E-RBAC-PAYROLL-TEACHER-06`, `E-RBAC-PAYROLL-TEACHER-07`, `E-RBAC-PAYROLL-TEACHER-08`, `E-RBAC-PAYROLL-TEACHER-09`, `E-RBAC-PAYROLL-TEACHER-10`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-01`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-03`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-04`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-05`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-06`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-07`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-08`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-09`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-10`

</details>

## Phase 09J

- **Salary structures.** Angular now opens editable drafts with their existing
  components populated. Administrator and payroll officer created, edited and
  activated drafts, verified decimal amounts on readback, and observed create
  and update audit events. The three other roles received permission-specific
  read and write denials without disclosure of the exact fixture salary. Active records rejected edits and preserved their persisted state.
- **Salary assignments.** The backend regression created a future assignment
  against a revised structure, verified allowance and deduction amounts,
  rejected overlapping and reversed date ranges, and compared finalized
  payroll before and after. Structure activation uses the active flag.
  Effective dates belong to the assignment. In-place assignment edits are
  rejected. Assignment termination remains unverified.
- **Separate approver.** The backend regression denied self-approval with the
  institution setting enabled, allowed a distinct authorized approver, denied
  finalization by an approver without the finalization grant, recorded the
  actors and verified immutable finalized entries.
- **Live authorization.** Removing the payroll officer's salary setup write
  grant denied draft creation and editing and future assignment creation,
  preserved the observed state, and removed edit controls on reload. A
  separate administrator control accepted the same requests. The teacher
  marks suite captured denial and state preservation after marks permissions
  were withdrawn and successful submission after restoration.
- **Mobile.** The administrator operated leave policy and balance, staff
  calendar, and retention workflows at 390×844. Leave processing verified
  carry limits and expiration, contract-specific monthly entitlement, duplicate
  prevention, and preserved historical ledger entries. The calendar distinguished
  overnight, absent, approved leave, and unrecorded dates. The retention
  workflow checked metadata and history, revised the review date, placed and
  released a hold, archived the document, and confirmed an authorized
  download returned the original bytes.

| Verification | Result | Evidence |
| --- | --- | --- |
| PostgreSQL regression | 56 passed, plus 6 subtests | `/tmp/sms09j-pg-final.log` |
| SQLite regression | 48 passed, 8 skipped, plus 6 subtests | `/tmp/sms09j-sqlite-final.log` |
| Django checks and migration consistency | System checks clean, no pending model changes | `manage.py check` and `makemigrations --check --dry-run` |
| Angular | Lint and type-check passed, 35 unit tests passed | `/tmp/sms09j-angular-final.log` |
| Angular production build | Passed, 898.08 kB initial bundle | `frontend/dist/school` |
| Playwright baseline | 5 passed, 3 configured skips | `/tmp/sms09j-baseline/results.json` |
| Playwright five-role salary revisions | 5 passed | `/tmp/sms09j-desktop-release/results.json` |
| Playwright mobile revisions | 1 passed | `/tmp/sms09j-mobile-closeout/results.json` |
| Playwright teacher marks and revocation | 1 passed | `/tmp/sms09j-teacher/results.json` |

Remaining scope includes the five-role non-payroll write matrix, remaining
financial access and grant-revocation scenarios, independent approval
controls for other payroll-related actions, effective-dated leave policy
revision, and the mobile items shown below. All browser data and signing keys
were disposable. The Phase 09 acceptance status is **INCOMPLETE**. Phase 10
has not started.

### Phase 09J checklist reconciliation

| Total | PASS | FAIL | BLOCKED | NOT TESTED | NOT APPLICABLE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 211 | 97 | 0 | 0 | 114 | 0 |

**Newly passing (23)** · `E-LEAVE-01`, `E-LEAVE-02`, `E-LEAVE-03`, `E-LEAVE-06`, `E-LEAVE-08`, `E-LEAVE-12`, `E-MOB-05`, `E-MOB-06`, `E-DOC-04`, `E-DOC-06`, `E-DOC-07`, `E-DOC-08`, `E-DOC-09`, `E-DOC-10`, `E-MOB-10`, `E-CAL-04`, `E-CAL-06`, `E-CAL-07`, `E-EXAM-01`, `E-EXAM-12`, `E-RBAC-PAYROLL-HR_OFFICER-01`, `E-RBAC-PAYROLL-TEACHER-01`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-01`

<details>
<summary>Exact remaining checklist IDs</summary>

- **LEAVE** (1) · `E-LEAVE-11`
- **MOB** (3) · `E-MOB-01`, `E-MOB-02`, `E-MOB-07`
- **RBAC EMPLOYEES** (9) · `E-RBAC-EMPLOYEES-ADMINISTRATOR-01`, `E-RBAC-EMPLOYEES-ADMINISTRATOR-04`, `E-RBAC-EMPLOYEES-HR_OFFICER-04`, `E-RBAC-EMPLOYEES-TEACHER-01`, `E-RBAC-EMPLOYEES-TEACHER-04`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-01`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-04`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-04`
- **RBAC DOCUMENTS** (10) · `E-RBAC-DOCUMENTS-ADMINISTRATOR-01`, `E-RBAC-DOCUMENTS-ADMINISTRATOR-02`, `E-RBAC-DOCUMENTS-HR_OFFICER-01`, `E-RBAC-DOCUMENTS-HR_OFFICER-02`, `E-RBAC-DOCUMENTS-TEACHER-01`, `E-RBAC-DOCUMENTS-TEACHER-02`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-01`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-02`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-01`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-02`
- **RBAC ATTENDANCE** (20) · `E-RBAC-ATTENDANCE-ADMINISTRATOR-01`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-02`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-03`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-04`, `E-RBAC-ATTENDANCE-HR_OFFICER-01`, `E-RBAC-ATTENDANCE-HR_OFFICER-02`, `E-RBAC-ATTENDANCE-HR_OFFICER-03`, `E-RBAC-ATTENDANCE-HR_OFFICER-04`, `E-RBAC-ATTENDANCE-TEACHER-01`, `E-RBAC-ATTENDANCE-TEACHER-02`, `E-RBAC-ATTENDANCE-TEACHER-03`, `E-RBAC-ATTENDANCE-TEACHER-04`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-01`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-02`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-03`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-04`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-01`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-02`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-03`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-04`
- **RBAC LEAVES** (25) · `E-RBAC-LEAVES-ADMINISTRATOR-01`, `E-RBAC-LEAVES-ADMINISTRATOR-02`, `E-RBAC-LEAVES-ADMINISTRATOR-03`, `E-RBAC-LEAVES-ADMINISTRATOR-04`, `E-RBAC-LEAVES-ADMINISTRATOR-05`, `E-RBAC-LEAVES-HR_OFFICER-01`, `E-RBAC-LEAVES-HR_OFFICER-02`, `E-RBAC-LEAVES-HR_OFFICER-03`, `E-RBAC-LEAVES-HR_OFFICER-04`, `E-RBAC-LEAVES-HR_OFFICER-05`, `E-RBAC-LEAVES-TEACHER-01`, `E-RBAC-LEAVES-TEACHER-02`, `E-RBAC-LEAVES-TEACHER-03`, `E-RBAC-LEAVES-TEACHER-04`, `E-RBAC-LEAVES-TEACHER-05`, `E-RBAC-LEAVES-PAYROLL_OFFICER-01`, `E-RBAC-LEAVES-PAYROLL_OFFICER-02`, `E-RBAC-LEAVES-PAYROLL_OFFICER-03`, `E-RBAC-LEAVES-PAYROLL_OFFICER-04`, `E-RBAC-LEAVES-PAYROLL_OFFICER-05`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-02`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-03`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-04`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-05`
- **RBAC OVERTIME** (20) · `E-RBAC-OVERTIME-ADMINISTRATOR-01`, `E-RBAC-OVERTIME-ADMINISTRATOR-02`, `E-RBAC-OVERTIME-ADMINISTRATOR-03`, `E-RBAC-OVERTIME-ADMINISTRATOR-04`, `E-RBAC-OVERTIME-HR_OFFICER-01`, `E-RBAC-OVERTIME-HR_OFFICER-02`, `E-RBAC-OVERTIME-HR_OFFICER-03`, `E-RBAC-OVERTIME-HR_OFFICER-04`, `E-RBAC-OVERTIME-TEACHER-01`, `E-RBAC-OVERTIME-TEACHER-02`, `E-RBAC-OVERTIME-TEACHER-03`, `E-RBAC-OVERTIME-TEACHER-04`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-01`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-02`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-03`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-04`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-01`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-02`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-03`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-04`
- **RBAC PAYROLL** (26) · `E-RBAC-PAYROLL-ADMINISTRATOR-09`, `E-RBAC-PAYROLL-ADMINISTRATOR-10`, `E-RBAC-PAYROLL-HR_OFFICER-03`, `E-RBAC-PAYROLL-HR_OFFICER-04`, `E-RBAC-PAYROLL-HR_OFFICER-05`, `E-RBAC-PAYROLL-HR_OFFICER-06`, `E-RBAC-PAYROLL-HR_OFFICER-07`, `E-RBAC-PAYROLL-HR_OFFICER-08`, `E-RBAC-PAYROLL-HR_OFFICER-09`, `E-RBAC-PAYROLL-HR_OFFICER-10`, `E-RBAC-PAYROLL-TEACHER-03`, `E-RBAC-PAYROLL-TEACHER-04`, `E-RBAC-PAYROLL-TEACHER-05`, `E-RBAC-PAYROLL-TEACHER-06`, `E-RBAC-PAYROLL-TEACHER-07`, `E-RBAC-PAYROLL-TEACHER-08`, `E-RBAC-PAYROLL-TEACHER-09`, `E-RBAC-PAYROLL-TEACHER-10`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-03`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-04`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-05`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-06`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-07`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-08`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-09`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-10`

</details>

## Phase 09K

The desktop HR matrix checked the configured effective grants of five
fixture roles. Each tested write used a valid, isolated payload. Denials
were checked against administrator readback before the same request was
allowed through an administrator control. For allowed actions, the suite
operated the Angular form and verified persisted fixture state. It closed
the remaining employee, document, staff attendance, leave authorization,
and overtime role-matrix IDs.

The financial run covered payroll preview, generation, approval, finalization,
payments, payslips, printing, and export. It checked Angular routes and controls
and verified that denied transactions preserved fixture state. In the same
payroll session, live grant withdrawals blocked preview, generation,
submission, review, approval, finalization, payment reversal, payroll
adjustment, and advance disbursement. Payroll and advance routes were
then denied. The browser also checked denied payslip, report export and
payment access and restored the fixture grants.

The overtime fixture with separate approval enabled rejected the requester's
decision and preserved the pending snapshot. A distinct authorized
administrator approved the same request. Salary advance approval has an
independent grant. This run verified advance disbursement revocation.
A dated salary assignment can be selected by its initial end date,
and the fresh regression verified future revisions and immutable finalized
payroll. Shortening an existing assignment through a supported termination
operation remains unverified. This phase did not implement approval policies
for adjustments, reversals or salary revisions.

At 390×844, the administrator created a teaching assignment, changed its end
date, observed both audit history entries, and separately approved an overtime
request. A fresh revision run verified overnight calendar differentiation,
leave carry and duplicate prevention, and the retention lifecycle. It
preserved the previously recorded document review date after revising the
retention policy. The five-role document matrix separately verified private
document listing and exact downloads.

No application code changed. During development, seed and browser assertions
were corrected to use a valid managed leave ledger fixture, filter the exact
leave policy, and link the teaching fixture employee to a user.

| Verification | Result | Evidence |
| --- | --- | --- |
| PostgreSQL regression | 56 passed, plus 6 subtests | `/tmp/sms09k-workflows.log` |
| SQLite regression | 48 passed, 8 skipped, plus 6 subtests | `/tmp/sms09k-sqlite.log` |
| Django and Python | System checks, migration consistency, and Ruff passed | `/tmp/sms09k-sqlite.log` and Ruff terminal output |
| Angular | 35 tests passed, type-check and lint passed | `/tmp/sms09k-angular.log` |
| Production build | Passed, 898.08 kB initial bundle | `/tmp/sms09k-angular.log` |
| Five-role desktop HR matrix | 10 passed | `/tmp/sms09k-desktop-release/results.json` |
| Five-role desktop finance | 5 passed | `/tmp/sms09k-finance-release/results.json` |
| Teaching assignments and overtime at 390 px | 2 passed | `/tmp/sms09k-mobile-final/results.json` |
| Leave, calendar, and retention at 390 px | 1 passed | `/tmp/sms09k-calendar-retention/results.json` |

`E-LEAVE-11` remains open. The leave type currently supports an accrual start
and in-place editing. Verification requires a supported way to schedule a
future policy revision and select its terms by accrual period, with tests
showing that posted credits and consumption survive the revision. Phase 09
remains **INCOMPLETE**. Phase 10 has not started.

### Phase 09K checklist reconciliation

| Total | PASS | FAIL | BLOCKED | NOT TESTED | NOT APPLICABLE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 211 | 210 | 0 | 0 | 1 | 0 |

<details>
<summary>Newly passing checklist IDs</summary>

- **MOB** (3) · `E-MOB-01`, `E-MOB-02`, `E-MOB-07`
- **EMPLOYEES** (9) · `E-RBAC-EMPLOYEES-ADMINISTRATOR-01`, `E-RBAC-EMPLOYEES-ADMINISTRATOR-04`, `E-RBAC-EMPLOYEES-HR_OFFICER-04`, `E-RBAC-EMPLOYEES-TEACHER-01`, `E-RBAC-EMPLOYEES-TEACHER-04`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-01`, `E-RBAC-EMPLOYEES-PAYROLL_OFFICER-04`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-EMPLOYEES-RESTRICTED_EMPLOYEE-04`
- **DOCUMENTS** (10) · `E-RBAC-DOCUMENTS-ADMINISTRATOR-01`, `E-RBAC-DOCUMENTS-ADMINISTRATOR-02`, `E-RBAC-DOCUMENTS-HR_OFFICER-01`, `E-RBAC-DOCUMENTS-HR_OFFICER-02`, `E-RBAC-DOCUMENTS-TEACHER-01`, `E-RBAC-DOCUMENTS-TEACHER-02`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-01`, `E-RBAC-DOCUMENTS-PAYROLL_OFFICER-02`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-01`, `E-RBAC-DOCUMENTS-RESTRICTED_EMPLOYEE-02`
- **ATTENDANCE** (20) · `E-RBAC-ATTENDANCE-ADMINISTRATOR-01`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-02`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-03`, `E-RBAC-ATTENDANCE-ADMINISTRATOR-04`, `E-RBAC-ATTENDANCE-HR_OFFICER-01`, `E-RBAC-ATTENDANCE-HR_OFFICER-02`, `E-RBAC-ATTENDANCE-HR_OFFICER-03`, `E-RBAC-ATTENDANCE-HR_OFFICER-04`, `E-RBAC-ATTENDANCE-TEACHER-01`, `E-RBAC-ATTENDANCE-TEACHER-02`, `E-RBAC-ATTENDANCE-TEACHER-03`, `E-RBAC-ATTENDANCE-TEACHER-04`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-01`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-02`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-03`, `E-RBAC-ATTENDANCE-PAYROLL_OFFICER-04`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-01`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-02`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-03`, `E-RBAC-ATTENDANCE-RESTRICTED_EMPLOYEE-04`
- **LEAVES** (25) · `E-RBAC-LEAVES-ADMINISTRATOR-01`, `E-RBAC-LEAVES-ADMINISTRATOR-02`, `E-RBAC-LEAVES-ADMINISTRATOR-03`, `E-RBAC-LEAVES-ADMINISTRATOR-04`, `E-RBAC-LEAVES-ADMINISTRATOR-05`, `E-RBAC-LEAVES-HR_OFFICER-01`, `E-RBAC-LEAVES-HR_OFFICER-02`, `E-RBAC-LEAVES-HR_OFFICER-03`, `E-RBAC-LEAVES-HR_OFFICER-04`, `E-RBAC-LEAVES-HR_OFFICER-05`, `E-RBAC-LEAVES-TEACHER-01`, `E-RBAC-LEAVES-TEACHER-02`, `E-RBAC-LEAVES-TEACHER-03`, `E-RBAC-LEAVES-TEACHER-04`, `E-RBAC-LEAVES-TEACHER-05`, `E-RBAC-LEAVES-PAYROLL_OFFICER-01`, `E-RBAC-LEAVES-PAYROLL_OFFICER-02`, `E-RBAC-LEAVES-PAYROLL_OFFICER-03`, `E-RBAC-LEAVES-PAYROLL_OFFICER-04`, `E-RBAC-LEAVES-PAYROLL_OFFICER-05`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-01`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-02`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-03`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-04`, `E-RBAC-LEAVES-RESTRICTED_EMPLOYEE-05`
- **OVERTIME** (20) · `E-RBAC-OVERTIME-ADMINISTRATOR-01`, `E-RBAC-OVERTIME-ADMINISTRATOR-02`, `E-RBAC-OVERTIME-ADMINISTRATOR-03`, `E-RBAC-OVERTIME-ADMINISTRATOR-04`, `E-RBAC-OVERTIME-HR_OFFICER-01`, `E-RBAC-OVERTIME-HR_OFFICER-02`, `E-RBAC-OVERTIME-HR_OFFICER-03`, `E-RBAC-OVERTIME-HR_OFFICER-04`, `E-RBAC-OVERTIME-TEACHER-01`, `E-RBAC-OVERTIME-TEACHER-02`, `E-RBAC-OVERTIME-TEACHER-03`, `E-RBAC-OVERTIME-TEACHER-04`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-01`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-02`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-03`, `E-RBAC-OVERTIME-PAYROLL_OFFICER-04`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-01`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-02`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-03`, `E-RBAC-OVERTIME-RESTRICTED_EMPLOYEE-04`
- **PAYROLL** (26) · `E-RBAC-PAYROLL-ADMINISTRATOR-09`, `E-RBAC-PAYROLL-ADMINISTRATOR-10`, `E-RBAC-PAYROLL-HR_OFFICER-03`, `E-RBAC-PAYROLL-HR_OFFICER-04`, `E-RBAC-PAYROLL-HR_OFFICER-05`, `E-RBAC-PAYROLL-HR_OFFICER-06`, `E-RBAC-PAYROLL-HR_OFFICER-07`, `E-RBAC-PAYROLL-HR_OFFICER-08`, `E-RBAC-PAYROLL-HR_OFFICER-09`, `E-RBAC-PAYROLL-HR_OFFICER-10`, `E-RBAC-PAYROLL-TEACHER-03`, `E-RBAC-PAYROLL-TEACHER-04`, `E-RBAC-PAYROLL-TEACHER-05`, `E-RBAC-PAYROLL-TEACHER-06`, `E-RBAC-PAYROLL-TEACHER-07`, `E-RBAC-PAYROLL-TEACHER-08`, `E-RBAC-PAYROLL-TEACHER-09`, `E-RBAC-PAYROLL-TEACHER-10`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-03`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-04`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-05`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-06`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-07`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-08`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-09`, `E-RBAC-PAYROLL-RESTRICTED_EMPLOYEE-10`

</details>

<details>
<summary>Exact remaining checklist IDs</summary>

- **LEAVE** (1) · `E-LEAVE-11`

</details>

## Phase 09L

**Checklist result · 211 PASS of 211.** `E-LEAVE-11` passed on desktop
and at 390×844. No checklist IDs were added or renamed. Phase 09 remains
**INCOMPLETE** because sensitive salary structure activation approval remains
open outside the checklist. Phase 10 has not started.

### Leave policy and ledger

Migration `hr.0012_leave_policy_versions` creates an initial published
version per existing leave type. It leaves ledger IDs, keys, actors, dates,
and amounts untouched. Ledger rows posted before the upgrade carry an
unknown version reference. New accruals record the version, period bounds,
eligible days, entitlement and any applied contract override.

A monthly revision starts on a month boundary. Transitions involving an
annual, fixed, or legacy method start January 1. Each published version
ends immediately before its successor. January terms govern the year's
carry limit and expiry. The contract covering the first eligible day
overrides the institution entitlement for that period. Existing posting
keys and the institution write lock prevent duplicate credits and conflicting
publications. A version already in use has no supported edit operation.

Angular can view policy history, save a draft, schedule a revision, withdraw
an unused latest revision and preview a future accrual through the Django
API. An authorized HR reader can still see history. Scheduling, withdrawal,
and accrual posting require both the appropriate grant and the signed,
current HR entitlement.

### E-LEAVE-11 evidence

The administrator created a leave type, employee and contract through Angular.
The original monthly policy posted six one-day credits. One approved leave
consumed one day, leaving five. The administrator scheduled a July revision
that doubled the monthly credit. The June and July previews selected distinct
versions at the expected boundary. Posting the July credit produced a balance
of seven and left the exact June ledger unchanged. Reposting produced no
duplicate. A separately signed-in HR reader received a permission-specific
403 and version history remained unchanged. The final screen passed the
viewport width and horizontal overflow assertions at both sizes. The test
advanced only the private runner's HR date.

| Verification | Result | Evidence |
| --- | --- | --- |
| PostgreSQL | 59 passed, plus 6 subtests | `/tmp/sms09l-mobile-final.log` |
| SQLite | 50 passed, 9 skipped, plus 6 subtests | `/tmp/sms09l-sqlite-final.log` |
| Populated upgrade from HR 0011 to 0012 | Baseline backfilled and existing ledger fields preserved | `/tmp/sms09l-migration.log` |
| Django checks, migration consistency, Ruff | Passed | `/tmp/sms09l-sqlite-final.log` and Ruff terminal output |
| Angular | 35 tests, lint, and type-check passed | `/tmp/sms09l-build.log` |
| Production build | Passed, 903.23 kB initial bundle | `/tmp/sms09l-build.log` |
| Desktop browser | 1 passed | `/tmp/sms09l-desktop-final/results.json` |
| Mobile browser | 1 passed | `/tmp/sms09l-mobile-final/results.json` |
| Baseline browser regression | 5 passed, 3 configured skips | `/tmp/sms09l-baseline/results.json` |

### Payroll scope dispositions

| Area | Original scope, implementation and evidence | Disposition |
| --- | --- | --- |
| Salary assignment termination | Phase 09 lists GET and POST assignments and requires effective dates and historical preservation. `hr/payroll.py` selects by dated assignment and rejects overlaps. The regression verifies future assignments and immutable finalized payroll. | Shortening a saved assignment is a deferred extension. |
| Salary advances | Phase 09 lists an advance approval endpoint. `Advances` requires the advance approval grant and approval before disbursement. Existing tests cover approval and disbursement, and Phase 09K tested disbursement grant revocation. | Existing scoped approval verified. A different approver is not a configured requirement. |
| Payroll adjustments and payment reversals | Phase 09 requires controlled adjustments and reversals. `hr/payroll.py` uses the correction grant and audits each mutation. Phase 09K verified denial after grant withdrawal and state preservation. | Existing controls verified. Additional dual approval is a separately defined policy enhancement. |
| Salary revision approval | Phase 09 §12 requires approval for sensitive salary structure changes. `Structures` protects active or referenced versions, and activation is audited and restricted to the salary setup grant. The available workflow has no explicit approval decision before activation. | Open outside the 211-ID checklist. Define and verify the explicit approval step before Phase 09 closure. |

### Phase 09L follow-up verification

The repeat brief matched Phase 09L. The follow-up strengthened the original
evidence without adding checklist IDs or changing production code.

- The license test activated a signed fixture license and advanced only the
  verifier clock. The expired license denied policy revision and accrual
  writes. Authorized readers could still see identical version and ledger
  history.
- The carry test scheduled a January revision, verified five days credited
  and later expired under that revision, and checked the old ledger entry
  remained exactly the same. An injected audit failure rolled back the carry
  credit. A retry posted it once.
- The PostgreSQL concurrency test scheduled next year's revision while
  posting current accrual. Both writes succeeded, and the posted amount and
  version still matched the original terms.

The explicit approval decision for sensitive salary structure activation
remains the open item outside the fixed checklist. The prior dispositions
for assignment termination, advances, adjustments and reversals still apply.

| Fresh verification | Result | Evidence |
| --- | --- | --- |
| PostgreSQL | 61 passed, plus 6 subtests | `/tmp/sms09l-recheck-pg-final.log` |
| SQLite and Django checks | 51 passed, 10 skipped, plus 6 subtests. System and migration consistency checks passed. | `/tmp/sms09l-recheck-sqlite-final.log` |
| Angular | 35 passed. Lint, type-check and the 903.23 kB production build passed. | `/tmp/sms09l-recheck-angular.log` |
| E-LEAVE-11 desktop | 1 passed | `/tmp/sms09l-recheck-desktop/results.json` |
| E-LEAVE-11 mobile | 1 passed | `/tmp/sms09l-recheck-mobile-final/results.json` |

## Phase 09M supplemental acceptance

**Requirement** · Explicit approval of sensitive salary structure revisions
prior to activation. This requirement is tracked outside the fixed 211-ID
checklist.

The prior create and edit paths accepted the `active` flag under the salary
setup grant and recorded a generic write event. The new workflow separates
draft creation, submission, approval or rejection, and activation. The
salary approval service validates compensation, effective dates, approval
identity and exact snapshot. A later edit creates a new revision. It cannot
reuse an earlier approval. An approval or activation conflict rolls back
within the institution write transaction. Rejection requires a reason.

The approval model stores the reviewed terms, actors, decision and activation
timestamps. Audit events refer to the structure, approval ID and revision
without including salary amounts. The institution setting defaults to
separate approval. In this mode, neither the creator nor the submitter can
approve the request, including administrators. A request submitted under the
separation policy keeps that requirement after a settings change. An explicit
decision is required even when the institution permits self-approval.

Migration `hr.0013_salary_structure_approval` identifies existing active
structures as legacy. It adds no approval rows for those structures and
preserves existing components, assignments, finalized payroll, and payments.
The populated migration probe checked the exact before and after records.
Fresh browser tests also checked that assigning the approved structure to a
new future interval preserved the prior finalized run, payslip and payment.

The protected administrator role receives distinct submission, history,
decision, and activation grants. Other roles need explicitly assigned grants.
The isolated browser tests verified permissions and live decision grant
revocation. The signed-license test verified expired write denial, existing
approval and payroll reads, printable payslips, available export, and
renewal followed by successful approval and activation.

### Dispositions

- Salary assignment termination remains deferred. The original API requires
  list and create for dated assignments. A successor assignment uses a
  non-overlapping interval, and existing assignments remain historical.
- Advances require approval before disbursement. Payroll periods and overtime
  policies enforce separate approvers when configured. Payment reversals
  and adjustments retain dedicated grants and audit trails. Further dual
  approval for those corrections would be a separate institutional policy.
- Salary structure revisions use the explicit approval workflow delivered in
  this phase. The 211 fixed checklist entries and their evidence are unchanged.

| Verification | Result | Evidence |
| --- | --- | --- |
| Desktop Chromium | 4 passed, including the full workflow and three denied-role cases | `/tmp/sms09m-acceptance-desktop/results.json` |
| Chromium at 390×844 | 1 passed, including review, rejection, resubmission, approval, activation and historical readback | `/tmp/sms09m-acceptance-mobile/results.json` |
| PostgreSQL | 64 passed, plus 6 subtests | `/tmp/sms09m-acceptance-mobile.log` |
| SQLite, system and migration consistency checks | 53 passed, 11 skipped, plus 6 subtests. Checks passed. | `/tmp/sms09m-acceptance-sqlite.log` |
| Populated legacy migration | Passed | `/tmp/sms09m-migration-final.log` |
| Angular | 35 passed. Lint, type-check and production build passed. Initial bundle 910.74 kB. | `/tmp/sms09m-angular.log` |
| Regression browser suites | Finance 5 passed, salary revisions 5 passed, leave 1 passed, baseline 5 passed and 3 configured skips | `/tmp/sms09m-finance`, `/tmp/sms09m-revisions`, `/tmp/sms09m-leave`, `/tmp/sms09m-baseline` |

**Supplemental approval acceptance · PASS. Fixed checklist · 211 of 211
PASS. FINAL PHASE 09 STATUS · COMPLETE.** Phase 10 has not started.
