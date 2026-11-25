# Employee attendance and leave

Staff attendance uses its own employee and date record. Missing dates are
unrecorded. Supervisors can mark individually or submit a transaction-safe
bulk request. Correct an existing date with an explicit reason. The correction
keeps previous and revised values. Employment dates and contracted weekdays
govern eligibility when a contract exists.

Configure leave types and paid annual entitlements before approval. Requests
cover a single calendar year and count employment working days. Pending and
approved requests cannot overlap. Approval consumes the paid annual entitlement.
Cancellation restores the balance. Approved unpaid leave is recorded for review
and does not create an automatic statutory deduction.

Use the attendance and monthly attendance reports to filter recorded days by
department, employee or status. Monthly totals count recorded statuses.
The dashboard reports unrecorded employees separately.

Employment contracts accept overnight shifts when the shift end time precedes
the start time. Use the start date when recording an overnight shift. Break and
tolerance settings are entered as whole minutes. Breaks reduce hourly payroll
duration, while the monthly employee calendar applies the tolerance settings.

Configure a department schedule template to prefill an employee's dated
contract. The calendar uses the stored contract schedule, including for prior
months after a department template changes.

The [Phase 09 acceptance report](PHASE_09_ACCEPTANCE_REPORT.md) records desktop
and mobile calendar results and the remaining filter and status scenarios.

Phase 09D verified employee and department filters, month changes, and rendered
status distinctions through Angular on desktop and at 390 px. Corrections and
correction history still require browser acceptance.

Use **Correction history** on an attendance row to review prior and revised values and the recorded reason.

Leave policy revisions retain each approved request and its dates. The staff
calendar continues to classify approved leave by the existing request interval.
Accrual version changes affect leave entitlement and the ledger.

Published timetables display existing HR approved leave, absence and schedule
warnings. Dated substitutions are stored in timetables and leave employee
attendance, contracts and leave decisions intact.
