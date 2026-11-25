import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const [artifact, suite] = process.argv.slice(2);
if (!artifact || !['employee', 'exam'].includes(suite)) {
  throw new Error('Usage: node update-security-evidence.mjs <results.json> employee|exam');
}
const report = JSON.parse(readFileSync(artifact));
function allSpecs(suites) {
  return suites.flatMap(item => [...(item.specs ?? []), ...allSpecs(item.suites ?? [])]);
}
const specs = allSpecs(report.suites);
const source = new URL('./checklist.json', import.meta.url);
const rows = JSON.parse(readFileSync(source));
const evidence = new Map();

function fromReport(title, project, name) {
  const specsForProject = specs.filter(spec => spec.title === title)
    .flatMap(spec => spec.tests.filter(test => test.projectName === project));
  const result = specsForProject.length === 1 ? specsForProject[0].results.at(-1) : undefined;
  const attachment = result?.attachments.find(item => item.name === name);
  if (result?.status !== 'passed' || !attachment?.body) {
    throw new Error('Missing passing test or evidence attachment for ' + title);
  }
  return JSON.parse(Buffer.from(attachment.body, 'base64').toString());
}

function record(id, behavior, test, role, type, endpoint, route) {
  if (evidence.has(id)) throw new Error('Duplicate scenario evidence for ' + id);
  evidence.set(id, {
    behavior, test, role, type, endpoint, route, viewport: '1440x900',
    artifact: resolve(artifact), result: 'PASS',
  });
}

if (suite === 'employee') {
  const roles = {
    admin: 'ADMINISTRATOR', hr: 'HR_OFFICER', teacher: 'TEACHER',
    payroll: 'PAYROLL_OFFICER', restricted: 'RESTRICTED_EMPLOYEE',
  };
  for (const [role, code] of Object.entries(roles)) {
    const title = 'five-role read matrix for ' + role;
    const { outcomes } = fromReport(title, 'role-matrix', 'role-outcomes');
    for (const [operation, id, endpoint, route] of [
      ['employee-create', '02', 'POST /api/v1/hr/employees/', '/hr/employees/new'],
      ['employee-edit', '03', 'PATCH /api/v1/hr/employees/:id/', '/hr/employees/:id'],
    ]) {
      const outcome = outcomes.find(item => item.operation === operation);
      if (!outcome?.verifiedPersistence || ![200, 201, 403].includes(outcome.status)) {
        throw new Error('Missing verified write outcome for ' + role + ': ' + operation);
      }
      if (role === 'hr' && id === '03' && !outcomes.some(item =>
        item.operation === 'employee-edit-revoked' && item.status === 403 && item.verifiedPersistence)) {
        throw new Error('Missing live HR edit revocation evidence.');
      }
      record('E-RBAC-EMPLOYEES-' + code + '-' + id,
        outcome.status === 403 ? 'Denied. Control could perform the same request. No unauthorized data change.'
          : 'Angular submitted the authorized form and control confirmed the persisted change.',
        title, role, ['Angular browser workflow', 'API authorization'], endpoint, route);
    }
  }
} else {
  const title = 'E-ATT-02 to E-ATT-10 teacher attendance scope and operational denials';
  const outcomes = fromReport(title, 'desktop', 'exam-scope');
  for (const [name, id] of [
    ['unrelated-class', 'E-EXAM-02'], ['unrelated-subject', 'E-EXAM-03'],
    ['unrelated-section', 'E-EXAM-04'], ['future', 'E-EXAM-05'], ['inactive', 'E-EXAM-07'],
  ]) {
    const outcome = outcomes.find(item => item.name === name);
    if (outcome?.allowed !== 200 || outcome.denied !== 404) {
      throw new Error('Missing controlled examination scope outcome for ' + name);
    }
    record(id, 'Administrator read the existing submission. Teacher received 404 for ' + name + '.',
      title, 'Teacher and administrator control', ['API authorization'],
      'GET /api/v1/examinations/marks/:id/', '/examinations/marks');
  }
}
for (const [id, proof] of evidence) {
  const row = rows.find(item => item.id === id);
  if (!row) throw new Error('Unknown checklist ID ' + id);
  row.phase09hEvidence = proof;
  row.phase09hTraceability = {
    requiredEvidence: proof.type,
    coverage: 'recorded',
    verificationSource: 'phase09hEvidence',
  };
  row.result = 'PASS';
  row.verificationClassification = 'ALREADY_VERIFIED';
  row.missingEvidence = null;
  delete row.openReason;
}
writeFileSync(source, JSON.stringify(rows, null, 2) + '\n');
