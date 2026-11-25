# Fee management

Phase 07 uses the existing institution, student and effective-dated enrollment.
An invoice references the enrollment used to calculate it and retains its
original line amounts. Changing a structure, moving a student or withdrawing
a student leaves posted transactions intact.

Billing uses the latest placement overlapping a cycle as of the cycle closing
date. Enrollment end dates are exclusive. The first eligible date is the later
of admission and enrollment dates. Transfers and promotions use the placement
selected for that cycle. Withdrawal and graduation stop future charges.
Re-enrollment permits new charges once the new placement takes effect.

Monthly generation identifies a line by student, session, category and month.
One-time charges require a stable reference. Each billing transaction locks
the institution before reading financial state and committing the batch.
An explicitly enabled proration policy allocates monthly fees over calendar days.
Approved concessions are category-scoped or general and capped at the gross fee.

Financial configuration and mutations use the existing role matrix, CSRF-aware
session APIs, audit trail and signed fees entitlement. Configuration and invoice
operations are available offline. Refer to FINANCIAL_TRANSACTIONS.md for posting.

## Setup and billing

1. Open Fee Management. Create the categories and a draft fee structure for the
   academic session and class. Add fee lines and activate the structure.
2. Assign a student-specific structure or a category override when needed.
   A zero override exempts the student from that charge.
3. Create a fixed, percentage, or full concession. Use its label to distinguish
   merit, need-based, sibling or staff-child awards. An authorized user approves it.
4. Preview a billing month, review the missing-charge warnings, and issue the
   batch. The confirmation is tied to the previewed amounts. Review again when
   a fee plan changes between preview and issue.
5. Use a separate reference for a distinct one-time or custom charge. A repeated
   reference does not create a duplicate debt. Monthly fees use the month,
   quarterly fees the calendar quarter, term fees the academic session, and
   annual fees the calendar year for identity.

Section-specific structures take precedence over the class default. Active
structures covering the same exact scope cannot overlap. By default, the
largest applicable concession wins. When stacking is enabled, one category
concession and one general concession can apply, capped at the charge amount.
Proration is disabled by default. When enabled, the latest eligible placement
provides the monthly tariff and the day count starts at the placement start
within that month.

## Policies and reporting

Register due dates use the configured due day, clamped to the issue date and
available days in the selected month. The billing day sets the assessment day
for optional late fees. Late fees are disabled by default. To enable them,
create and activate a fee category with code LATE, set the amount and grace
days, and review the preview. Billing can apply one late fee per overdue
prior invoice with an outstanding balance.

Use Outstanding Fees for unpaid and overdue invoices. The reports page includes
cash collections, monthly trends, class and session balances, a student ledger,
payment methods, due-date aging, invoice and receipt registers, structures,
concessions and refunds or reversals. Financial reports and printable records
require their own permissions. CSV export uses UTF-8 with BOM and formula
escaping. Printable documents use local browser printing, including PDF where
supported.

## API and verification

API routes are relative to /api/v1/fees/.

- categories, structures, assignments, concessions and settings configure fees.
- billing/preview, billing/generate and billing/history manage batches.
- invoices and payments expose histories, challans and receipts.
- adjustments and refunds record reviewed corrections.
- students/{id}/statement and students/{id}/outstanding expose balances.
- reports/{kind} and reports/{kind}/export provide filtered reporting.

Run from the repository root:

    .venv/bin/python backend/manage.py check
    .venv/bin/python backend/manage.py makemigrations --check --dry-run
    .venv/bin/python -m ruff check backend
    .venv/bin/python -m pytest -q
    cd frontend
    npm run typecheck
    npm run lint
    npm test
    npm run build

Run PostgreSQL integration tests with a disposable UTF-8 database and an
isolated database role or local test socket. Use test-only signing keys and
verify that the backend and Angular proxy point at the isolated instance
before testing collection.
