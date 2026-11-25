# Human resources

Employees can optionally link to one existing login. Employment records and
payroll are separate from authentication and student fees. Teaching permissions
continue to use teaching assignments. Employment dates are inclusive. Changes
to positions create history, while payroll retains its original snapshots.
Writes are serialized using the institution lock and checked against RBAC and
the appropriate signed entitlement.

## Operations

Create departments and designations before adding employees. Employee codes
are operator-assigned and case-insensitively unique. Linked login accounts
are optional. The initial position and later changes are available on the
employee profile. Record employment contracts with effective dates and
working weekdays. Inactive historical contracts remain in the database.

Private employee documents accept still PNG, JPEG, and WebP scans using the
local image validation and size policy. They are normalized to PNG, downloaded
from authorized endpoints, and archived without deleting source rows.
Separate document permissions control reads and writes.

The /api/v1/hr/ routes cover employees, contracts, documents, attendance,
leave, compensation, payroll, payslips, and reports. HR writes use the signed
hr feature. Salary configuration and payroll writes use payroll. Reports,
history and payslip printing remain available with the appropriate permissions
when a license expires. Salary amounts use a separate grant from employee details.

From Ubuntu run bash scripts/start-dev.sh. Verify using Django check, migration
consistency, pytest and Ruff. Run TypeScript, ESLint, Vitest and the Angular
production build from frontend. Use an isolated PostgreSQL database and
test-only keys for workflow verification.

Configure the employee numbering prefix and next number in HR Settings.
Leaving the code blank generates an unused number while holding the institution
lock. The document-retention value records the institution policy. Archived
files remain available for authorized review.

## Phase 09B workflows

Use **Academic assignments** on an employee profile to create, end or change
assignments. Enter dates in the institution timezone. Leave a bound blank for
an open-ended assignment. To hand over a group, end the old assignment before
creating the overlapping scope for the new dates.

Use **Staff attendance** to open the monthly calendar for an employee. The
calendar shows recorded attendance, approved leave, institutional holidays,
nonworking days and gaps in recording. Overnight shifts belong to their start
date. Contracts define break duration and late and early tolerances in minutes.

Use **Leave types** to configure paid leave accrual. The legacy policy preserves
the original annual entitlement. Monthly accrual credits completed months.
Annual allocation can prorate by eligible calendar days and fixed annual
entitlement allocates the full amount. Use the leave balance panel to preview
and post accrual or enter a receipted opening balance or signed adjustment.
Opening balances are posted per employee, type and year. Calendar-year carry
uses the prior year's posted balance and the configured cap. Review and post
the prior year before processing the new year. Carry expiry is posted when
accrual runs through the expiry date. Review late corrections to closed years
and use a signed adjustment where needed.

Set retention defaults and per-type days under **HR settings**. The per-type
field accepts an object such as `{"contract":365,"identity":90}`. Upload stores
the review date under the policy in force at upload. For documents without a
review date, enter one through a retention extension. Use the **Retention
review queue** to see due documents and use the employee profile to review
history, extend the date, or place or release a hold. Archive requires a
released hold. These actions preserve the stored file.

To reuse a department schedule, enter a template under **Departments** and
select **Copy the department schedule** when creating an employment contract.
For example, a template can use
`{"weekdays":[0,1,2,3,4],"shift_start":"22:00","shift_end":"06:00","break_minutes":30}`.
Optional keys are `late_tolerance_minutes` and `early_tolerance_minutes`. The
contract stores its own copy, so editing the template affects future contracts.

On a contract, enter annual leave overrides by leave type code, for example
`{"ANNUAL":"18.50"}`. Accrual uses the contract covering the first eligible
day of each monthly or annual allocation. The override replaces the annual
amount before the policy's proration and balance cap are applied. Posted
amounts stay in the ledger when a later contract changes the entitlement.

### Verification

The full regression suites passed with 50 PostgreSQL tests and 43 SQLite tests.
Angular reported 34 passing tests, and the production build completed. Isolated
Chrome checks covered the calendar at desktop and 390 px widths. Desktop Chrome
also exercised the contract template, leave ledger, payroll and payslip APIs,
and confirmed payroll read restrictions and expired-license write denial. The
teaching assignment date boundaries were exercised by backend tests.

For the latest full-suite and browser results, see the
[Phase 09 acceptance report](PHASE_09_ACCEPTANCE_REPORT.md).

Phase 09D verified Angular leave accrual, approval, cancellation and ledger
reversal, plus document upload and retention decisions. See the
[acceptance report](PHASE_09_ACCEPTANCE_REPORT.md) for the tested permissions
and remaining edge cases.

The retention queue links authorized operators to the employee profile and private document download.

### Leave policy migration and compatibility

The leave type remains the stable identity for requests, overrides and ledger
entries. Existing policy settings become an initial version. Existing ledger
rows keep their amounts, dates and keys, and their version reference stays
empty because the terms originally applied cannot be reconstructed reliably.
New accrual and carry entries record the applied version and calculation
inputs. Monthly revisions start on the first of a month. Annual and fixed
revisions start on January 1. A new revision closes the prior version's
effective interval at its start date, using an exclusive upper boundary.

Open **Policy versions** on a leave type. Review the effective and upcoming
terms, then use **Schedule revision** to enter the effective date and new
terms. Save a draft for further editing or publish the revision. A manager can
withdraw the latest unused future revision or schedule terms with Active
cleared to stop new eligibility. A historical version cannot be edited from
the revision workflow.

Monthly accrual selects terms at the start of the month and posts at month end.
Annual, fixed, or legacy transitions require January 1. January 1 terms govern
carried balances and their expiry for that year. A contract covering the first
eligible day of the accrual period overrides the institution entitlement for
the stable leave code. Manual adjustments remain independent ledger entries.
The balance screen can preview a future date, and posting requires an elapsed
date. A historical lookup shows the ledger through the selected date.

In **Salary structures**, saving creates or updates a draft. The pending
approval queue, explicit decision, and activation are separate steps. Under
**HR settings**, the separate salary structure approver policy defaults to on.

Timetable teacher preferences are advisory. Effective hard workload
policies and hard unavailability remain blocking. Dated lesson changes
also consult linked employment, contracts and approved leave.
