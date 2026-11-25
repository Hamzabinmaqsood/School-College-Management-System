# Examination management

Examinations reuse the existing institution, session, class, subject, student,
dated enrollment, and teaching assignments. A class roster freezes the
placement effective on the exam start date. Enrollment intervals exclude the
end date. The receiving placement owns a same-day transfer. Published results
keep their original class, section, admission number, and roll number. Optional
subjects require an individual selection. An examination officer records
exceptions before opening the roster.

Configuration and scheduling remain editable while the examination is in
draft. Opening marks freezes configuration and roster. Teachers can access
only the session, class, section and subject in an active teaching assignment.
A separate institution-wide grant covers officers. Submissions freeze an entry
version, and verification is separate from entering marks.

The signed examinations entitlement controls writes. Authorized historical
reads, printed cards, and exports remain available after expiry. PostgreSQL
stores the source records and publication snapshots.

## Setup and workflow

1. Create an exam type and grading scheme.
2. Create an examination within the academic session and the scheme's effective dates.
3. Add participating classes, assign curriculum subjects, and configure components.
4. Add a date sheet. Overlapping schedules for the same class or room are rejected.
5. Enter roster exceptions or optional subject choices, then open marks entry.
6. Teachers save drafts and submit them. Reviewers verify or return submissions.
7. Calculate a draft class result, review the totals, approve it, and confirm publication.
8. Print the class date sheet and report cards or export the published results.

An exam can advance from draft to scheduled to marks entry. It can open directly
from draft when no public date sheet is needed. Closing requires publication for
every participating class. Effective classes and sections come from the historical
enrollment on the exam's start date. Exceptions are recorded against an existing
enrollment before marks entry opens.

## API and permissions

The routes under /api/v1/examinations/ cover types, grading-schemes, exams,
classes, subjects, schedules, registrations, marks, results, reports, and overview.
Marks and result workflow actions are POST operations on individual resources.
Stale marks versions return 409. Published result cards and exports are available
through GET endpoints with dedicated permissions.

A teaching assignment is exact to its session, class, section and subject.
The broad examinations scope is separate from the permission to enter,
verify, approve, publish, or correct. The protected administrator receives the
new grants. Configuration roles that use academic registry selectors also need
the corresponding registry read permissions.

## Verification and deployment

Run Django system checks, migration consistency, Ruff and pytest in Ubuntu.
For PostgreSQL workflows use an isolated UTF-8 database and test-only signing
keys. In frontend run npm run typecheck, npm run lint, npm test and npm run build.
The ordinary startup command is bash scripts/start-dev.sh.

Exam dates must fall within the configured exam period. Ordinary class scheduling
is outside this module. Use browser printing to save report cards as PDFs.

A timetable relocation checks the destination against scheduled examinations
for the section's class and matching room. Examination records and marks
remain under the existing examination workflow.
