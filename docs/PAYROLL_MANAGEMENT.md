# Payroll management

Calculations use Decimal, two PKR decimal places and half-up rounding. Monthly
proration is optional and uses actual calendar days. Payroll generation and
disbursement are separate. An employee can have one obligation per payroll
period. Finalized net salary is preserved. Outstanding payable deducts
recorded payments from authorized net liability.

Statutory deductions, employment entitlements, tax calculations and compliance
rules require configuration and verification for the applicable institution and
jurisdiction. The system supports configured adjustments and makes no automatic
statutory calculation.

## Generation and disbursement

Use active, effective-dated salary assignments. Monthly and contract salary
multiply the base by the configured proration factor, while fixed components
apply once per run entry. Daily and hourly pay use explicit attendance records
and configured working days. The system flags incomplete working schedules
or attendance for review. Unpaid leave deductions and overtime compensation
require an explicitly recorded component or authorized adjustment.

Approve and record an advance disbursement before recovery. A recovery uses
the agreed installment up to the remaining advance balance and available net.
Draft entries reserve recoveries. Preview the period and department before
generating. The preview key protects against changed source inputs. One
employee-period identity prevents duplicate obligations.

Submit, review, approve, and finalize a draft. A period can require a different
approver. Disburse separately, using a stable request key. Multiple payments
may settle one entry. A reversal retains the original payment and reinstates
the liability. Authorized adjustments change the payable balance while retaining
the original earned net. Print payslips locally or save them as PDF in the browser.

Hourly payroll calculates overnight shifts against the shift start date and
deducts the scheduled break. Overtime policies use a fixed hourly rate or monthly basic salary divided by
policy hours. A request references one staff attendance row. Approvers enter
hours within the configured threshold and maximum. The decision records
person, time, rate, multiplier, and amount. The institution calendar determines
holiday and working-day overrides. Otherwise, the contract determines rest days.
Payroll includes approved overtime by attendance date and displays the stored
decision details. Use a reviewed payroll adjustment for approval received after
finalization. Configure unpaid leave deductions on the salary structure by
setting an explicit daily rate for monthly or contract compensation.

The [Phase 09 acceptance report](PHASE_09_ACCEPTANCE_REPORT.md) records isolated
payroll finalization, payment retry, payable reconciliation and payslip checks.

Phase 09D reran the payroll regression suite and verified the direct Angular
payroll route and payroll list API under five isolated account grants. The
full role-by-operation matrix remains open.

Use the Phase 09 acceptance report for the current summary of payroll role coverage and remaining checks.

### Phase 09L scope review

The original salary-assignment API exposes list and create. An assignment's
end date limits payroll selection, and tests cover effective-dated future
versions, overlap rejection, and immutable finalized payroll. An operation to
shorten an already saved assignment is a deferred extension.

A payroll period and an overtime policy can require distinct approvers.
Advances have a separate approval permission and require approval before
disbursement. Adjustments and payment reversals have dedicated permissions and
audit trails. Phase 09L identified that the salary setup grant previously allowed activation
without a recorded decision. Phase 09M adds and verifies explicit approval
before activation. A two-person rule for adjustments, reversals, or advances would
require a separately defined policy.

### Phase 09M activation change

The previous salary structure create and edit endpoints accepted the active
flag from any salary setup manager. They recorded a write but no distinct
approval decision. Phase 09M moves activation to an explicit workflow.
Existing active structures and their assignments remain valid. Legacy active
structures have no manufactured approval or actor.

Save a draft in **Salary structures**, then submit it for approval. Open the
pending queue to review the submitted snapshot, including compensation
components and effective dates. Approve with explicit confirmation or
reject with a reason. Activate the approved revision separately. Editing
an inactive structure advances its revision and requires a new approval.
The history shows prior decisions, the actors and timestamps, and the exact
reviewed terms.

HR settings require separate approval by default. Under that policy, neither
the draft creator nor the submitter can approve. If the institution disables
separation, the approver still needs the dedicated approval grant and must
record an explicit decision. A pending request retains the separation
requirement in force at submission.

Structure dates bound new salary assignments when supplied. The assignment
still chooses the structure and controls employee-specific dates. Existing
assignments remain attached to their original structure. For a revision, create
and approve a distinct structure and use it in a later non-overlapping
assignment. Shortening a saved assignment remains outside the original
list-and-create API. Advances, overtime, adjustments, and reversals retain
their established approval and correction controls.
