import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const reports = [
  'class', 'section', 'teacher-weekly', 'teacher-daily', 'rooms', 'workload',
  'allocations', 'unassigned', 'conflicts', 'substitutions', 'cancellations',
  'reschedules', 'revisions', 'attendance',
];
const title = 'configures, reviews and publishes a scoped timetable';
const [artifact] = process.argv.slice(2);
if (!artifact) throw new Error('Usage: node update-timetable-evidence.mjs <results.json>');

function specs(suites) {
  return suites.flatMap(suite => [...(suite.specs ?? []), ...specs(suite.suites ?? [])]);
}

const report = JSON.parse(readFileSync(artifact, 'utf8'));
const tests = specs(report.suites).filter(spec => spec.title === title).flatMap(spec => spec.tests);
const valid = ['timetable-desktop', 'timetable-mobile'];
if (tests.length !== 1 || !valid.includes(tests[0].projectName)) {
  throw new Error('Expected one identified desktop or mobile timetable test.');
}
const run = tests[0];
const result = run.results.at(-1);
if (result?.status !== 'passed') throw new Error('The timetable test did not pass.');
const attachment = result.attachments.find(item => item.name === 'report-outcomes');
const closure = result.attachments.find(item => item.name === 'phase10e-closure');
const history = result.attachments.find(item => item.name === 'phase10f-history');
if (!attachment?.body && !closure?.body && !history?.body) throw new Error('Criterion assertions are missing.');
const outcomes = attachment?.body ? JSON.parse(Buffer.from(attachment.body, 'base64').toString('utf8')) : null;
if (outcomes && (outcomes.length !== reports.length || reports.some(reportName =>
  outcomes.filter(row => row.kind === reportName && Number.isInteger(row.count) &&
    row.from && row.through && row.export === reportName + '.csv').length !== 1))) {
  throw new Error('Incomplete report assertion evidence.');
}

const path = new URL('./timetable-checklist.json', import.meta.url);
const checklist = JSON.parse(readFileSync(path, 'utf8'));
const viewport = run.projectName === 'timetable-mobile' ? '390x844' : '1440x900';
if (outcomes) {
  const goal = checklist.find(row => row.id === 'TT-31');
  const key = history?.body ? 'phase10fReportEvidence' :
    closure?.body ? 'phase10eReportEvidence' : 'phase10dBrowserEvidence';
  goal[key] ??= {};
  goal[key][run.projectName] = {
    test: title,
    testType: 'Playwright',
    result: result.status,
    role: 'Institution administrator',
    route: '/timetable',
    fixture: 'Browser Academy disposable scheduling fixture',
    databaseAssertions: 'Backend fixture reconciliation is recorded separately.',
    viewport,
    artifact: resolve(artifact),
    finalCriterionStatus: goal.status,
    outcomes: outcomes.map(row => ({...row, endpoint: '/api/v1/timetables/reports/' + row.kind + '/'})),
  };
}
if (closure?.body) {
  const assertions = JSON.parse(Buffer.from(closure.body, 'base64').toString('utf8'));
  const checks = [
    ['TT-04', assertions.break, value => value?.id && value?.adjacent &&
      value.invalidStatus === 400 && value.persisted === true,
      'Created break and adjacent lessons in separate tested shifts; invalid placement was rejected without an entry.'],
    ['TT-06', assertions.classPlan, value => value?.id && value?.version &&
      value.entries === 2 && value.published === true,
      'Created a class/section plan in Angular, verified two entries and allocation, and published after review.'],
    ['TT-19', assertions.publication, value => value?.entry && value?.successor &&
      value.mutationStatus === 409 && value.notesUnchanged === true,
      'Published edit denied; successor published and original occurrence and notes preserved.'],
    ['TT-23', assertions.leave, value => value?.id && value.date && value.kind === 'substitute',
      'Approved leave displayed on the affected daily occurrence; substitution kept the recurring teacher.'],
  ];
  for (const [id, observed, verified, expected] of checks) {
    if (!verified(observed)) continue;
    const item = checklist.find(row => row.id === id);
    const key = history?.body ? 'phase10fEvidence' : 'phase10eEvidence';
    item[key] ??= {};
    item[key][run.projectName] = {
      test: title, testType: 'Playwright', result: result.status, expected, observed,
      role: 'Institution administrator with separate reviewer and teacher contexts',
      route: '/timetable', endpoint: '/api/v1/timetables/', viewport,
      artifact: resolve(artifact), finalCriterionStatus: item.status,
    };
  }
}
if (history?.body) {
  const observed = JSON.parse(Buffer.from(history.body, 'base64').toString('utf8'));
  if (!observed.source || !observed.destination || observed.source === observed.destination ||
      !observed.roster) throw new Error('Incomplete cross-version roster evidence.');
  for (const id of ['TT-19', run.projectName === 'timetable-mobile' ? 'TT-38' : 'TT-37']) {
    const item = checklist.find(row => row.id === id);
    item.phase10fHistoryEvidence ??= {};
    item.phase10fHistoryEvidence[run.projectName] = {
      test: title, testType: 'Playwright', result: result.status,
      expected: 'One destination occurrence uses the published successor roster and retains the original version reference.',
      observed, role: 'Institution administrator with separate reviewer context',
      route: '/timetable', endpoint: '/api/v1/timetables/exceptions/', viewport,
      artifact: resolve(artifact), finalCriterionStatus: item.status,
    };
  }
}
writeFileSync(path, JSON.stringify(checklist, null, 2) + '\n');
