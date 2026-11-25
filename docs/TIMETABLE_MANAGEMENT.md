# Timetable management

The **Timetable** workspace is available at `/timetable`. It uses the
existing academic session, class, section, curriculum, teacher assignments,
attendance calendar and HR records.

1. In **Configuration**, create a school shift and choose working weekdays
   using Monday = 0 through Sunday = 6. Add teaching periods and mark
   protected breaks as nonteaching. Add classrooms or laboratories and set
   their capacities where applicable.
2. Record hard teacher unavailability and optional weekly minimum and maximum
   subject allocations per session and section.
3. In **Plans and revisions**, choose the session, section, shift and
   dates. Add a required subject, eligible teacher and optional room.
   **Check conflicts** validates the draft. **Find available slots** proposes
   feasible periods for the selected subject, teacher and room.
4. Submit the version, have an authorized reviewer approve it, then publish.
   Separate review is on by default. Use **Copy to new draft** to revise a
   published timetable for a future date. Publication preserves the original
   dates and uses a separate supersession boundary.
5. Use **Published schedule** to filter by date, section, teacher or room.
   Daily and seven-day views support printing and grant-controlled CSV. The
   view includes teacher minutes, room usage and expected attendance
   registers for authorized users.
6. Use **Daily changes** to cancel a lesson, replace its teacher, or move it
   to a different period on the same day. A reason is required. Changes
   leave the weekly template and historical records intact.

The effective schedule reuses existing holiday and closure records. Approved
HR leave, recorded absence and out-of-contract hours surface warnings.
Replacement teachers must meet assignment and availability checks.
Examination display is read-only and respects exam permissions. Dates and
rooms are matched against existing examination records. Exam records are
maintained in the examination module.

Attendance links carry the published lesson's group, subject, date and period
to the existing register screen. A newly opened matching register stores a
small timetable snapshot. Existing, unscheduled and historical registers
remain usable. Teachers still need their original attendance scope to act.

## Deployment and tests

Apply migrations only after verifying an encrypted operational backup and
the pending migration plan. Phase 10 adds the timetable migrations and
`attendance.0004_timetable_snapshot`. The signed entitlement name is
`timetables`.

```bash
SMS_PHASE10=desktop bash frontend/tests/browser/phase09/run.sh
SMS_PHASE10=mobile SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
```

## Remaining scope

Phase 10B adds optional-subject teaching groups with explicit enrollment
membership per session, section and subject. A group is fixed after submission
so historical rosters stay reproducible. Grouped attendance uses actual
eligible members. Configure preferred or non-preferred time intervals with a
priority. They affect suggestions and warnings. Hard availability still blocks
scheduling.

Teacher workload policies can limit daily, weekly and consecutive periods
and enforce a clock-minute rest interval. A hard policy blocks conflicting
work. A soft policy reports warnings. Hard limits have no override action.

Dated rescheduling moves a lesson within its published version. The source and
destination are visible in the schedule, and reports count a move once.
Relocation is refused once original attendance exists. The destination is
checked against closures, assignment eligibility, availability, workload,
room and section conflicts, and overlapping examinations.

The report workspace exposes 14 report types with date and scope filters,
paginated JSON, and permission-controlled CSV. See the
[Phase 10 acceptance report](PHASE_10_ACCEPTANCE_REPORT.md) for what was
verified and what remains open.

## Phase 10 verification

Operational PostgreSQL answered a read-only query. The migration inventory
showed HR 0012 and 0013 pending. This run used disposable databases because an
encrypted, restorable operational backup had not been verified. No
operational migrations were applied.

- PostgreSQL regression and publication race · 67 tests and 6 subtests passed.
- SQLite regression · 55 passed, 12 skipped, plus 6 subtests. Django system
  checks and migration consistency passed.
- Desktop Chromium and 390×844 Chromium · one full workflow passed in each.
  Each run configured a shift, period and room, submitted and published with
  separate review, opened the teacher-scoped timetable, exported CSV, created
  an attendance register with its timetable snapshot, and cancelled the
  published lesson for the selected date.
- Desktop evidence is in `/tmp/sms10-desktop-acceptance/results.json`.
  Mobile evidence is in `/tmp/sms10-mobile-acceptance/results.json`.
- Signed-license testing covered expired configuration denial and continued
  access to published reads and authorized CSV. The full five-role matrix
  and live grant revocation still require timetable-specific coverage.

Phase 10 is **INCOMPLETE**. In addition to feature scope above, operational
deployment and full acceptance of the examination and HR edge cases remain
open. Phase 11 has not started.

Angular lint, TypeScript and 36 unit tests passed. The production build
passed with a 940.90 kB initial bundle. The pre-existing browser baseline
had 5 passes and 3 configured skips. Logs are `/tmp/sms10-regression.log`,
`/tmp/sms10-sqlite-final.log` and `/tmp/sms10-angular-acceptance.log`.


## Phase 10C report and print evidence

Class and own-scope teacher print layouts include the institution and published lesson revision context. Desktop and mobile Chromium verified print-media rendering. The [acceptance report](PHASE_10_ACCEPTANCE_REPORT.md) records representative data, pagination, CSV, and access checks for each of the 14 API reports. Full report filter, history, and printable variant checks remain open.

Phase 10D adds real Chromium class and teacher PDF artifacts to the acceptance
workflow, alongside a separate browser read and CSV download for each report.
Multi-page report PDFs and historical print variants still require verification.

The timetable configuration and lesson selector label non-teaching periods
as breaks. The Teaching period checkbox persists an unchecked value.
Overlapping intervals inside one shift and lesson placement into a break
are rejected by the timetable validation.

### Future-effective rosters and moves across revisions

Copy the published plan to a future draft. In the draft lesson, use
**Create successor roster** to create a roster for its existing optional
group. The draft lessons switch to the new roster. Edit its membership in
Configuration, then use the existing submit, review and publish workflow.
The copy retains students whose enrollment covers the future revision.

A rescheduling may target another published revision of the same plan.
Choose a teaching period that is valid on the destination date. The daily
schedule identifies the effective revision and retains the original lesson
reference. Existing attendance at either end blocks the move.
