# Teacher management

Link an employee to an existing active Django account when that person needs
application access. A teaching designation controls directory classification.
Attendance and examination access follow the permissions on the account and
its existing teaching assignments. The HR employee assignment endpoint adds
or deactivates those same records. The employee profile displays each assignment.

Assignment scope is the exact academic session, class, section, and subject.
A subject-free assignment applies to daily student attendance. Teaching
designation alone confers no access. Revoke an assignment or disable the
linked login separately when employment ends. Historical payroll keeps the
original employee and position details.

Phase 09B keeps TeachingAssignment as the authorization source. Existing records
start with open date bounds. Dates are inclusive in the institution timezone.
Operational access requires a valid assignment today and on the relevant
record date. Historical reads through an administratively enabled assignment
are limited to dates that assignment covered. Administratively disabled
assignments grant no access. Institution-wide history grants continue to apply.

On the employee profile, select **Assignment history** next to an assignment.
Authorized managers can review the recorded creation, date changes and
deactivation. Date change entries include the previous and new bounds.

A separately authenticated teacher saved and finalized a scoped attendance
register and saved and submitted marks through Angular in Phase 09D. See the
[acceptance report](PHASE_09_ACCEPTANCE_REPORT.md) for authorization coverage.

Phase 09E uses isolated Playwright fixtures for effective assignment checks. Consult the acceptance report for verified boundaries.
