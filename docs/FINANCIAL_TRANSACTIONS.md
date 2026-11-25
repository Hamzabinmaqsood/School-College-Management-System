# Financial transactions

PKR amounts use decimal arithmetic, two decimal places and half-up rounding.
Invoice totals derive from posted lines, debit and credit adjustments, and
net payment allocations. Issued invoice identifiers and amounts are immutable
through the application. Corrections use new financial events with an actor
and reason.

A payment must allocate its entire positive amount to invoices belonging to
one student. The client supplies an idempotency key. A retry with an identical
payload returns the original payment, and reuse with a different payload
returns a conflict. Overpayment and cross-student allocation are rejected.
A receipt captures the balances and document details at payment posting.
Reversal restores outstanding debt and retains the original receipt. Refunds
represent a separate cash event and reduce net applied payments.

Aging uses the due date and the institution's local date. Receipt and challan
printing uses offline HTML. A locally installed browser can print to PDF.

## Corrections and reconciliation

Adjustments are requested first and then approved with the dedicated grant.
Write-offs also require the write-off grant. Institution settings can require
a different user to approve. Credits and write-offs are capped at outstanding
debt. Refunds are tied to a payment allocation and capped at its remaining
refundable amount. Reversal is available for a payment without prior refunds.
An invoice without payment or adjustment history can be voided, retaining its
billing identity. The historical invoice and receipts remain accessible.

Receivables equal issued amounts plus approved debits, less approved credits,
write-offs and net applied payments. A voided invoice contributes zero.
Collection reports record the original cash receipt on the payment date and
subtract refunds and reversals on the dates those events occurred. This makes
refunds visible even when they fall in a different reporting month.
Receipt reprints retain the original amount, invoice references, and remaining
balances as of posting. Current reversal and refund notices are shown alongside
the original information. Institution logos use current branding.

Transactions serialize financial state changes under the institution lock. A
database unique constraint protects payment idempotency and another protects
billing line identity across generation batches. PostgreSQL NUMERIC values
and Python Decimal represent money. The collection form uses integer minor
units for the review total. A payment is fully allocated at posting, and overpayments
or cross-student payments are rejected.

## Scope

Billing generation is operator initiated. There is no background billing
scheduler, unapplied credit ledger, external bank verification or payment
gateway. Deployment must use UTF-8 PostgreSQL to retain Unicode snapshots.
