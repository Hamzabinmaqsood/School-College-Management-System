# Scheduling conflict rules

Timetable mutations run through the shared institution transaction lock.
The publication step rechecks all teaching entries under that lock. The
PostgreSQL race test requires exactly one successful competing publication
when two approved drafts reserve the same teacher and room.

- Real clock times use half-open intervals, so a lesson can start when
  another ends. The conflict engine checks common weekdays inside overlapping
  version date ranges across all shifts.
- A section, teacher or room cannot have simultaneous published lessons.
  Drafts are checked internally and against published schedules.
- A teaching period must be within the selected shift and cannot overlap a
  configured period or protected break. Lesson entries cannot use breaks.
- The selected teacher needs an active teaching assignment covering the
  recurring dates. Hard unavailability conflicts block the lesson.
- When room capacity checks are on, capacity must cover the active section
  roster. Configured subject weekly minima and maxima apply at review and
  publication.
- Effective dates are inclusive. A successor supersedes the previous version
  from a separate boundary; the original date range is retained. Existing
  future exceptions on the outgoing version block replacement.
- Dated changes check the actual day's section, teacher and room reservations.
  Holidays and closures suppress lessons without changing the weekly draft.
  Examination and HR conflicts are surfaced as warnings in published views.

### Optional groups and dated changes

Disjoint optional groups can meet in parallel within a section when teacher
and room reservations also differ. Overlapping student memberships and
full-section overlaps block parallel scheduling. A teaching group is bound
to its curriculum choice and enrollment scope.

Preferred and non-preferred times rank suggestions. Hard unavailability
remains blocking. Effective teacher workload policies check weekly actual
occurrences, including published reservations, candidate drafts and dated
changes. Soft policies emit warnings. Cross-date moves omit the original
reservation when checking the destination and retain the original
occurrence for history.


## Phase 10C integrity disposition

Published optional teaching group membership is frozen. Successor membership workflows require further work. Rescheduling currently targets the source published version. The hard workload limit blocks violations and no override is available. See the [acceptance report](PHASE_10_ACCEPTANCE_REPORT.md) for the current concurrency, HR leave, and examination evidence and gaps.

The original Phase 10 brief explicitly requires an authorized room-capacity
override. Its workload requirements do not specify an authorized exception
to a hard teacher workload limit. Phase 10C preserves hard enforcement.
Room-capacity override acceptance is a separate open case.

Cross-version moves would require both effective versions and the source
occurrence to be recorded, destination conflicts and policies to be checked,
and finalized attendance to be preserved. Existing moves within a published
version preserve the original occurrence and count the replacement once.

Phase 10D verifies that breaks cannot be booked and that pending or rejected
staff leave does not annotate an otherwise scheduled lesson. Approved leave
annotates its date without rewriting the recurring published lesson.

A break may share a boundary with an adjacent teaching period. Interval
overlap is validated per shift. A break cannot become the period on a lesson,
even if the request supplies its identifier directly.

Phase 10F resolves cross-version relocations against the destination
revision of the source plan. Conflict, workload, roster, holiday, exam,
teacher assignment and staff availability checks use that destination.
An existing dated move is considered when another plan attempts to reserve
the same effective resources. The room-capacity planning exception policy
remains open. This work preserves current room and workload enforcement.
