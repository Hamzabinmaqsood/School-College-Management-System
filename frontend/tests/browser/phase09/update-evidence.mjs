import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const [reportFile, kind] = process.argv.slice(2);
const known = {
  matrix: {
    title: 'five-role read matrix for hr',
    project: 'role-matrix',
    role: 'HR officer',
    assertions: {
      'E-RBAC-EMPLOYEES-HR_OFFICER-01':
        'Employee list and HR navigation initially allowed. Live role revocation denied the same list and direct route, removed the link after refresh, and returned no employee rows.',
    },
  },
  workflow: {
    title: 'E-ATT-02 to E-ATT-10 teacher attendance scope and operational denials',
    project: 'desktop',
    role: 'Teacher and administrator control',
    assertions: {
      'E-EXAM-09': 'Teacher approval of the existing calculated result returned 403. Administrator control approval returned 200.',
      'E-EXAM-10': 'Teacher publication of the existing approved result returned 403. Administrator publication of the same result returned 200.',
    },
  },
};
const run = known[kind];
if (!reportFile || !run) throw new Error('Usage: node update-evidence.mjs <results.json> matrix|workflow');

const report = JSON.parse(readFileSync(reportFile, 'utf8'));
function specs(suites) {
  return suites.flatMap(suite => [...(suite.specs ?? []), ...specs(suite.suites ?? [])]);
}
const matches = specs(report.suites).filter(spec => spec.title === run.title)
  .flatMap(spec => spec.tests.filter(test => test.projectName === run.project));
if (matches.length !== 1 || matches[0].results.at(-1)?.status !== 'passed') {
  throw new Error('The expected test and project must have recorded a passing result.');
}
if (kind === 'matrix') {
  const attachment = matches[0].results.at(-1).attachments.find(item => item.name === 'role-outcomes');
  const details = JSON.parse(Buffer.from(attachment?.body ?? '', 'base64').toString());
  if (!details.outcomes.some(item => item.endpoint === 'employees/ after revocation' && item.actual === 403)) {
    throw new Error('The report must contain the live revocation outcome.');
  }
} else {
  const statuses = readFileSync(join(dirname(reportFile), 'http-statuses.log'), 'utf8');
  const denial = statuses.match(/^POST (\/api\/v1\/examinations\/results\/[0-9a-f-]+\/)publish\/ 403$/m);
  if (!denial || !statuses.includes('POST ' + denial[1] + 'publish/ 200') ||
      !statuses.includes('POST ' + denial[1] + 'approve/ 403') ||
      !statuses.includes('POST ' + denial[1] + 'approve/ 200')) {
    throw new Error('The request evidence must show allowed and denied operations on the same result.');
  }
}
const path = new URL('./checklist.json', import.meta.url);
const checklist = JSON.parse(readFileSync(path, 'utf8'));
for (const [id, actual] of Object.entries(run.assertions)) {
  const item = checklist.find(row => row.id === id);
  if (!item) throw new Error('Unknown scenario ' + id);
  item.phase09gEvidence = {
    test: run.title, testType: 'Playwright', role: run.role,
    viewport: '1440x900', expected: item.expected, actual,
    artifact: resolve(reportFile), status: 'PASS',
  };
  item.result = 'PASS';
  item.verificationClassification = 'ALREADY_VERIFIED';
  item.missingEvidence = null;
  delete item.openReason;
}
writeFileSync(path, JSON.stringify(checklist, null, 2) + '\n');
