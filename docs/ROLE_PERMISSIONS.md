# Roles and permissions

Django Group stores memberships and permissions. Role stores its UUID,
description, activation state, system designation, and timestamps. The
accounts migrations attach active role metadata to existing groups. The
idempotent seed_roles command creates missing permission rows and ten role
templates, preserving configured templates when rerun. Institution
Administrator receives the supported catalog. Other system templates initially
receive dashboard access.

Effective application permissions are the union of Django direct grants and
grants from active roles, restricted to the application catalog. Multiple
roles can be assigned. Direct grants are visible in the effective-permissions
API and require local Django administration to change. Deactivated accounts
have no effective grants. Revocation takes effect on the next API request.
Angular renders allowed links, guards routes, and refreshes access as the user
navigates or returns focus to the application.

Users may delegate only grants they possess. The installation administrator
role is protected. Its membership changes require an installation
administrator, and the last operational administrator cannot be deactivated
or lose that role. The application does not create staff or superusers.
Account and role mutations use transactions and serialize authority changes
before rechecking the actor's access.

The roles page loads the permission matrix from /api/v1/permissions/.
Unsupported actions are disabled. Reserved grants expose planned module pages
without exposing business data. Temporary passwords and sensitive user
information are excluded from audit change metadata. Audit logs are
read-only in the application.

## Phase 05 grants

Existing academic view grants become active registry access. Student detail, guardians, document access, export, print, and progression each require their own grants. The data migration adds the Phase 05 grants to the protected institution administrator. Ordinary templates are unchanged. Operators who enter admissions also need read grants for the lookups they use.

## Phase 06 attendance

Action permissions and teaching-group access are independent. Institution-wide attendance scope requires accounts.scope_all_attendance. Other users need a matching active teaching assignment.

See [Attendance management](ATTENDANCE_MANAGEMENT.md) for daily and period registers, historical enrollment, leave, calendar, permissions, licensing, APIs and test commands.

## Phase 07 fee management

See [Fee management](FEE_MANAGEMENT.md) for effective-dated structures, billing, PostgreSQL transactions, dynamic financial permissions, the signed fees entitlement and verification commands. Use UTF-8 PostgreSQL.

## Phase 08 examinations

See [Examination management](EXAMINATION_MANAGEMENT.md) for historic rosters, grading, marks verification, publication, corrections and the signed examinations entitlement.

## Phase 09 human resources and payroll

See [Human resources](HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

## Phase 09B grants

| Operation | Existing grant |
| --- | --- |
| Manage assignment dates via the employee profile | View teachers and manage teaching assignments |
| Read the staff calendar and department totals | View staff attendance |
| Read the leave ledger and accrual preview | View staff leave |
| Post accrual, openings or adjustments | Approve staff leave |
| Configure leave and retention defaults | Manage HR registry |
| Read overtime and salary calculations | View payroll |
| Configure and submit overtime | Generate payroll |
| Decide overtime | Approve payroll and satisfy the policy's separate-approver rule |
| Review or extend document retention | Manage employee documents |

Reference [HR workflows](HR_MANAGEMENT.md) for the operator steps.

Leave policy version history uses `accounts.view_staff_leave`. Draft,
schedule and withdrawal actions use `accounts.manage_hr_registry`. Posting
accrual and adjusting balances use `accounts.approve_staff_leave`.

Salary structure management (`accounts.manage_salary_setup`) permits draft
edits. `accounts.submit_salary_structure` submits a revision.
`accounts.view_salary_structure_approvals` reads the pending queue and history.
`accounts.approve_salary_structure` records approval or rejection.
`accounts.activate_salary_structure` activates the approved revision.
The migration adds these permissions to the protected institution administrator
role. Other staff require explicit grants.

The timetable migration grants configuration, drafting, submission, approval,
publication, exception and export rights to the protected institution
administrator. Teacher templates receive `accounts.view_own_timetable`,
which limits published schedules to the signed-in teacher. Other timetable
duties use explicit dynamic grants. Approval remains subject to the
institution's separate-review policy.

Teaching group setup uses timetable management permissions. Membership
lookup and display additionally require the student view grant. Teacher
schedule views never return group member lists. Live approval revocation
uses the existing dynamic role permission mechanism.


## Timetable approval grant revocation

On desktop and mobile Chromium, an already signed-in reviewer lost approval access immediately when the approval grant was revoked. The API returned HTTP 403, the revision stayed in review, and the approval control disappeared after reload. The full five-role operation matrix and remaining live revocation cases are still open in the [Phase 10 acceptance report](PHASE_10_ACCEPTANCE_REPORT.md).

Timetable printing uses the browser for schedule or report data already
loaded under the corresponding read grant. A dedicated print grant and
live print-control revocation have not been verified. CSV requests use
the separate timetable export grant.

Phase 10D verifies that a timetable read grant can open a report while CSV
export independently requires the timetable export grant.

Phase 10E treats curriculum and teacher eligibility validation separately
from role permission checks. The scheduler tests use authorized disposable
accounts for validation failures. The broader five-role timetable matrix
remains tracked in the Phase 10 acceptance checklist.

Creating an optional-group successor requires both timetable management and
student viewing. The successor still follows the existing timetable approval
and publication grants. Cross-version moves use the existing daily-exception
grant and licensing rules.
