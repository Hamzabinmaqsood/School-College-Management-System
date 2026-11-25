import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const [desktop, mobile, teacher, teacherMobile] = process.argv.slice(2);
if (![desktop, mobile, teacher, teacherMobile].every(Boolean)) {
  throw new Error('Usage: node update-financial-evidence.mjs <finance desktop> <finance mobile> <teacher desktop> <teacher mobile>');
}
const file = new URL('./checklist.json', import.meta.url);
const rows = JSON.parse(readFileSync(file));
const updates = new Map();

function specList(suites) {
  return suites.flatMap(suite => [...(suite.specs ?? []), ...specList(suite.suites ?? [])]);
}

function evidence(fileName, title, project, attachmentName) {
  const reports = specList(JSON.parse(readFileSync(fileName)).suites)
    .filter(spec => spec.title === title)
    .flatMap(spec => spec.tests.filter(t => t.projectName === project));
  const result = reports.length === 1 ? reports[0].results.at(-1) : undefined;
  const attachment = result?.attachments.find(a => a.name === attachmentName);
  if (result?.status !== 'passed' || !attachment?.body) throw new Error('Missing passing report for ' + title);
  return JSON.parse(Buffer.from(attachment.body, 'base64').toString());
}

function record(id, artifact, test, role, viewport, behavior) {
  if (updates.has(id)) throw new Error('Duplicate verification for ' + id);
  updates.set(id, { artifact: resolve(artifact), test, role, viewport, behavior, result: 'PASS' });
}

const roles = { admin: 'ADMINISTRATOR', hr: 'HR_OFFICER', teacher: 'TEACHER',
  payroll: 'PAYROLL_OFFICER', restricted: 'RESTRICTED_EMPLOYEE' };
const financial = {
  '01': 'salary-structures-view', '02': 'salary-assignments/', '03': 'payroll/preview/',
  '04': 'payroll/generate/', '05': '/approve/', '06': '/finalize/',
  '07': 'salary-payments/', '08': 'payslips-view', '09': 'payslip-print', '10': 'payroll-export',
};
for (const [role, identifier] of Object.entries(roles)) {
  const title = 'finance access and transaction controls for ' + role;
  const { outcomes } = evidence(desktop, title, 'finance-desktop', 'finance-outcomes');
  const codes = role === 'admin' ? ['01', '02', '03', '04', '05', '06', '07', '08']
    : role === 'payroll' ? Object.keys(financial) : ['02'];
  for (const code of codes) {
    const action = financial[code];
    const result = outcomes.find(item => item.operation?.endsWith(action) &&
      ((role === 'admin' || role === 'payroll') ? item.ui : item.roleStatus === 403 && item.beforeVerified));
    if (!result) throw new Error('No matching action result for ' + role + ' ' + action);
    const id = 'E-RBAC-PAYROLL-' + identifier + '-' + code;
    record(id, desktop, title, role, '1440x900',
      result.ui ? 'Operated the Angular control and verified the successful fixture outcome.'
        : 'Route denied. The API returned a permission-specific 403, preserved state, and allowed the administrator control.');
    updates.get(id).actual = result;
    updates.get(id).type = result.ui ? ['Angular browser workflow', 'API authorization']
      : ['Angular route guard', 'API authorization'];
  }
}
const mobileTitle = 'finance access and transaction controls for payroll';
const mobileOutcomes = evidence(mobile, mobileTitle, 'finance-mobile', 'finance-outcomes').outcomes;
for (const [id, actions] of [['E-MOB-08', ['/review/', '/finalize/']], ['E-MOB-09', ['payslip-print']]]) {
  if (!actions.every(action => mobileOutcomes.some(item => item.ui && item.operation.endsWith(action)))) {
    throw new Error('Missing required mobile controls for ' + id);
  }
  record(id, mobile, mobileTitle, 'Payroll officer', '390x844', 'Operated the Angular controls at 390 px.');
}
const teacherTitle = 'teacher exam writes and live attendance and marks grant revocation';
const teacherOutcomes = evidence(teacher, teacherTitle, 'teacher-writes', 'teacher-write-outcomes');
for (const [id, scenario, behavior] of [
  ['E-EXAM-06', 'expired', 'Expired assignment denied a valid marks save. Existing marks were unchanged and the administrator could save.'],
  ['E-ATT-11', 'teacher grant revocation', 'Live attendance write revocation preserved the roster, removed the draft action, and restoration allowed the write.'],
]) {
  if (!teacherOutcomes.some(item => item.scenario === scenario && item.unchanged)) throw new Error('Missing ' + scenario);
  record(id, teacher, teacherTitle, 'Teacher', '1440x900', behavior);
}
evidence(teacherMobile, teacherTitle, 'teacher-writes', 'teacher-write-outcomes');
record('E-MOB-03', teacherMobile, teacherTitle, 'Teacher', '390x844',
  'Saved and submitted marks through the Angular roster at 390 px.');

for (const [id, proof] of updates) {
  const row = rows.find(item => item.id === id);
  if (!row) throw new Error('Unknown ID ' + id);
  row.phase09iEvidence = { ...proof, type: proof.type ?? (id.startsWith('E-MOB-')
    ? ['Mobile browser'] : ['API authorization', 'Angular browser workflow']),
    requirement: row.requirement, route: row.angularRoute,
    endpoint: row.backendEndpoint, expected: row.expected };
  row.result = 'PASS';
  row.verificationClassification = 'ALREADY_VERIFIED';
  row.missingEvidence = null;
  delete row.openReason;
}
writeFileSync(file, JSON.stringify(rows, null, 2) + '\n');
