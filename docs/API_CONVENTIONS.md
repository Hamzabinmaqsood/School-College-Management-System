# API Conventions

## 1. Transport

The REST API uses JSON. Django REST Framework provides versioned paths such as `/api/v1/`. Standalone or LAN deployment may use HTTPS; local HTTP is permitted only on loopback or a segregated trusted LAN.

## 2. Resource conventions

- Nouns and plural resource names;
- `GET`, `POST`, `PATCH`, `PUT`, and `DELETE` only as appropriate;
- nested routes for genuine ownership and unambiguous subresources;
- server-generated UUIDs;
- cursor or keyset pagination for large lists.

Example:

```text
GET  /api/v1/students/
POST /api/v1/students/
GET  /api/v1/students/{id}/
PATCH /api/v1/students/{id}/
```

## 3. Response shape

List responses use pagination metadata. Individual operations return the resource or a stable operation record.

Errors use:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "The request could not be completed.",
  "details": {
    "field": ["Human-readable field error"]
  }
}
```

Use HTTP 400 for validation, 401 for unauthenticated, 403 for authorization/license/write denial, 404 for missing/hidden resources, 409 for conflicts, 422 for domain invariants, and 503 for unavailable services.

## 4. Authorization

Every endpoint declares required permission codes. Object-level checks run after model lookup. License write enforcement applies after authentication and before mutation.

## 5. Validation and transactions

DRF serializers validate field shape and cross-field input. Domain services enforce invariants in PostgreSQL transactions. Financial and other multi-row operations set an idempotency key.

## 6. Audit

Mutating endpoints log actor, permission, resource, action, IP, and before/after state or a redacted structured delta. Read logging is configurable for sensitive endpoints.

## 7. Localization

API error codes are stable; human-readable messages are translated by the frontend or backend locale selection. Dates use ISO 8601, while academic dates use explicit `YYYY-MM-DD` fields.

## Phase 03 endpoints

All paths use the /api/v1/ prefix. Authentication provides GET auth/csrf/ and auth/me/, plus POST auth/login/, auth/logout/, and auth/change-password/. Institution supports GET and PATCH institution/ and GET institution/logo/. Users support GET and POST users/, GET and PATCH users/{uuid}/, GET permissions/ below a user, and POST activate/, deactivate/, and reset-password/ below a user. Roles support GET and POST roles/, GET, PATCH and DELETE roles/{uuid}/, and GET and PUT roles/{uuid}/permissions/. GET permissions/ lists modules and action codes. GET audit/ and audit/{uuid}/ are read-only. Lists use offset and limit with count, next, previous, and results. Mutations require a current CSRF token. The institution form uses multipart PATCH for logo upload.

## Licensing API

GET /api/v1/license/status/ returns lifecycle state and authorized metadata. GET /api/v1/license/installation/ returns both IDs and activation ability. POST /api/v1/license/activate/ accepts a JSON token or a multipart file and returns 201 for activation, 200 for an idempotent import, or 400/409 for validation and conflicts. GET /api/v1/license/history/ lists signature-verified activations with offset pagination. Business gates return HTTP 403 with code LICENSE_WRITE_DENIED and a machine-readable status.

## Academic and student API

Collections under /api/v1/ are academic-sessions, classes, sections, subjects, class-subjects, students, guardians, and admissions. Student actions include summary, history, print, enrollment-report, export, guardian links and private documents. Admissions accepts either nested JSON or multipart with a JSON payload and indexed document fields. Enrollment actions include promote, repeat, transfer, transfer-out, withdraw, graduate, and re-enroll. Mutations are session, CSRF, permission, and license checked.

## Phase 06 attendance

The attendance API uses institution and teaching-assignment scope. Mutations compare the submitted register version and return 409 on stale edits.

See [Attendance management](ATTENDANCE_MANAGEMENT.md) for daily and period registers, historical enrollment, leave, calendar, permissions, licensing, APIs and test commands.

## Phase 07 fee management

See [Fee management](FEE_MANAGEMENT.md) for effective-dated structures, billing, PostgreSQL transactions, dynamic financial permissions, the signed fees entitlement and verification commands. Use UTF-8 PostgreSQL.

## Phase 08 examinations

See [Examination management](EXAMINATION_MANAGEMENT.md) for historic rosters, grading, marks verification, publication, corrections and the signed examinations entitlement.

## Phase 09 human resources and payroll

See [Human resources](HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

## Phase 09B HR routes

Routes below are relative to `/api/v1/hr/`.

| Method and route | Purpose |
| --- | --- |
| `PATCH employees/{id}/assignment-dates/` | Change an existing assignment's inclusive bounds and audit the change |
| `GET attendance/calendar/?employee={id}&month=YYYY-MM` | Monthly employee schedule, attendance, leave and overtime duration |
| `GET attendance/calendar/?department={id}&month=YYYY-MM` | Monthly recorded attendance counts by date and status |
| `GET leave-balances/` | Read the annual posted balance and preview accrual through the requested date |
| `POST leave-balances/apply/` | Post the accrual preview idempotently |
| `POST leave-balances/adjust/` | Post an opening balance or signed adjustment with a UUID key and reason |
| `GET, POST overtime-policies/` | List or create effective-dated compensation policies |
| `GET, POST overtime/` | Read or submit attendance-linked overtime |
| `POST overtime/{id}/decision/` | Approve or reject a request and store its calculation inputs |
| `GET documents/due/` | Page through due, unarchived document reviews |
| `GET documents/{id}/reviews/` | Read retention decision history |
| `POST documents/{id}/retention/` | Extend, place a hold or release a hold with a reason |

Leave balance requests use `employee`, `leave_type` and `through`. Policy
management uses the existing `leave-types/` route. The student attendance
assignment route also accepts `effective_start` and `effective_end`.

`GET /api/v1/hr/leave-types/{id}/versions/` returns version history.
`POST` on that URL saves a draft or schedules a revision using
`effective_start`, `terms`, and optional `draft`.
`POST /api/v1/hr/leave-types/{id}/withdraw-version/` takes the latest eligible
scheduled version ID. Leave balances accept `preview=1` for read-only
future projections. Apply and adjustment still require an elapsed date.

Salary structure actions are `POST {id}/submit/`, `approve/`, `reject/`,
and `activate/` under `/api/v1/hr/salary-structures/`. Decision and activation
requests identify the approval UUID in `approval`. Rejection requires
`reason`. The `GET {id}/approvals/` history and `GET pending-approvals/`
queue require the history grant. Stale decisions and incomplete transitions
return conflict responses. Direct draft activation fields are rejected.

Timetables uses `/api/v1/timetables/`. Configuration resources include
`settings/`, `shifts/`, `periods/`, `rooms/`, `teacher-availability/` and
`subject-requirements/`. Plan endpoints expose `versions/`, `new-version/`,
`subject-allocation/`, and transitions `submit/`, `approve/`, `reject/` and
`publish/`. Lesson mutation uses `entries/`. `validate/` and
`suggestions/` support drafting. `exceptions/` records dated changes.
Use `daily/`, `weekly/` and `reports/export/` with date and optional scope
filters. Configured scope conflicts return HTTP 409.

Phase 10B adds `teaching-groups/`, `group-members/`, and
`workload-policies/`. Dated exception payloads may include
`destination_date` for rescheduling. Dedicated `reports/{kind}/` routes
use shared schedule data. The same routes accept `format_type=csv` for
authorized export. Report date ranges are capped at 31 days.
