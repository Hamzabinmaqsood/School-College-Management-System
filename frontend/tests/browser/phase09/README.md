# Phase 09 browser acceptance

Run from Ubuntu WSL with the project's Python environment, Node.js, and local
PostgreSQL binaries available. Playwright needs Chrome Headless Shell and its
Linux runtime libraries. Install development dependencies and the browser once
on the test machine.

```bash
cd frontend
npm ci
npx playwright install chromium --only-shell
cd ..
bash frontend/tests/browser/phase09/run.sh
```

Use `--project=mobile` or `--grep E-CAL-01` to focus a run. Use
`SMS_PHASE09_CHROME` for an existing compatible Linux Chrome executable.
The server defaults are localhost ports 8039 and 4239. Override them with
`SMS_PHASE09_DJANGO_PORT` and `SMS_PHASE09_ANGULAR_PORT` when needed.

The launcher initializes a private PostgreSQL cluster in a temporary directory,
runs migrations, generates disposable fixture credentials and licensing keys,
and stops its own processes on exit. It writes the JSON report to the printed
evidence directory. Traces, screenshots, and videos are disabled to keep login
credentials and sensitive fixture content out of retained evidence.

`checklist.json` tracks unverified acceptance scenarios. Browser checks and
direct API assertions are identified separately in the acceptance report.

The suite builds and serves the Angular production bundle. It records HTTP
methods, paths, and status codes for fixture requests, without headers,
credentials, or session cookies. If Chrome reports a missing Linux shared
library, install the Playwright-provided system dependencies on the QA machine
or set `SMS_PHASE09_CHROME` to a compatible Chrome already available there.

Run the five-role browser matrix as a separate invocation. This keeps fixture
grants isolated and avoids combining both suites' sign-ins in one throttle
window. To also rerun the full database regression inside its disposable cluster,
set `SMS_PHASE09_PG_REGRESSION=1`.

```bash
SMS_PHASE09_MATRIX=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
```

Before tests begin, the launcher checks the PostgreSQL database name, server
data directory, and Unix-socket connection. It then verifies the unique fixture
institution UUID through the frontend proxy. The role report contains expected
and actual statuses without recording credential or cookie values.

Phase 09H adds employee create and edit controls to the role matrix. Denial
tests verify the original data persists and use a separate administrator
request context to execute the same payload. Passing reports can update the
checklist through `update-security-evidence.mjs <results.json> employee` or
`update-security-evidence.mjs <results.json> exam`. The importer requires the
specific attached outcomes before writing a scenario status.

Phase 09I uses dedicated finance and teacher-write runs. The same fixture
isolation checks apply to every invocation. The finance matrix assigns each
role its own payroll period and retains a separate finalized read fixture.

```bash
SMS_PHASE09_FINANCE=desktop SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_FINANCE=mobile bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_TEACHER=desktop bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_TEACHER=mobile bash frontend/tests/browser/phase09/run.sh
```

Pass the four resulting JSON reports in that order to
`update-financial-evidence.mjs` to import verified outcomes.

## Phase 09J salary revisions

From the repository root, run these commands sequentially. The revision
suite uses the finance fixtures for salary permissions and assignments.

```bash
SMS_PHASE09_REVISIONS=desktop SMS_PHASE09_FINANCE=desktop SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_REVISIONS=mobile SMS_PHASE09_FINANCE=mobile bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_TEACHER=desktop bash frontend/tests/browser/phase09/run.sh
```

Use `SMS_PHASE09_EVIDENCE` to choose a report directory and
`SMS_PHASE09_DJANGO_PORT` and `SMS_PHASE09_ANGULAR_PORT` to select unused ports.
The mobile revision project runs at 390×844. Its JSON report includes a
`revision-outcomes` attachment after the browser assertions finish.

## Phase 09K HR and financial matrix

Use the four commands in the root README. For evidence reconciliation, provide
the optional `SMS_PHASE09_EVIDENCE` directory separately for each run and pass
the resulting report paths in desktop workflows, mobile workflows, and
desktop finance order.

```bash
node frontend/tests/browser/phase09/update-workflow-evidence.mjs \
  /tmp/hr-desktop/results.json /tmp/hr-mobile/results.json /tmp/hr-finance/results.json
```

The importer checks the report project, outcome per checklist ID, viewport,
and passing test status. Existing passing rows are preserved.

## Phase 09L effective-dated leave

`SMS_PHASE09_LEAVE=desktop` and `SMS_PHASE09_LEAVE=mobile` run the full
revision, accrual, historical ledger and permission scenario. The launcher
uses a private PostgreSQL cluster and a test-only Django settings module.
Playwright advances the HR date through a file in that cluster's temporary
directory. The operating system date and license clock stay unchanged.

```bash
node frontend/tests/browser/phase09/update-leave-evidence.mjs \
  /tmp/leave-desktop/results.json /tmp/leave-mobile/results.json
```

## Phase 09M salary approval

```bash
SMS_PHASE09_APPROVAL=desktop SMS_PHASE09_FINANCE=desktop bash frontend/tests/browser/phase09/run.sh
SMS_PHASE09_APPROVAL=mobile SMS_PHASE09_FINANCE=mobile SMS_PHASE09_PG_REGRESSION=1 bash frontend/tests/browser/phase09/run.sh
```

Run sequentially. Finance fixtures provide finalized payroll and a distinct
fixture account for prior salary activation. The browser checks use separate
maker and reviewer sessions. The supplemental approval evidence belongs in
the acceptance report. The fixed checklist retains its original 211 IDs.
