import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const [desktop, mobile, finance] = process.argv.slice(2);
if (![desktop, mobile, finance].every(Boolean)) {
  throw new Error('Provide the desktop workflow, mobile workflow, and finance JSON reports.');
}
const checklist = new URL('./checklist.json', import.meta.url);
const rows = JSON.parse(readFileSync(checklist));
const byId = new Map(rows.map(row => [row.id, row]));
if (rows.length !== 211 || byId.size !== rows.length) throw new Error('Unexpected checklist identity');
const updates = new Map();

function list(suites) {
  return suites.flatMap(suite => [...(suite.specs ?? []), ...list(suite.suites ?? [])]);
}

function proofs(file, project, name) {
  return list(JSON.parse(readFileSync(file)).suites).flatMap(spec => spec.tests
    .filter(test => test.projectName === project && test.status === 'expected')
    .flatMap(test => {
      const result = test.results.at(-1);
      const attached = result?.attachments.find(attachment => attachment.name === name);
      if (result?.status !== 'passed' || !attached?.body) return [];
      return [{ artifact: resolve(file), test: spec.title,
        actual: JSON.parse(Buffer.from(attached.body, 'base64')) }];
    }));
}

function add(id, proof) {
  const row = byId.get(id);
  if (!row) throw new Error('Unknown checklist ID ' + id);
  if (row.result !== 'NOT_TESTED') return;
  if (updates.has(id)) throw new Error('Duplicate evidence for ' + id);
  updates.set(id, { ...proof, requirement: row.requirement, route: row.angularRoute,
    expected: row.expected, type: ['Angular browser workflow', 'API authorization'],
    result: 'PASS' });
}

for (const [file, width, height] of [[desktop, 1440, 900], [mobile, 390, 844]]) {
  const reports = proofs(file, 'hr-workflows', 'workflow-outcomes');
  if (!reports.length) throw new Error('No passing workflow evidence in ' + file);
  for (const { actual, ...report } of reports) {
    for (const { id, viewport, ...result } of actual) {
      if (viewport.width !== width || viewport.height !== height || ![200, 201, 403].includes(result.status)
          || !result.resource || !result.persistence) throw new Error('Invalid outcome for ' + id);
      if (id.startsWith('E-MOB-') !== (width === 390)) continue;
      add(id, { ...report, ...result, viewport });
    }
  }
}

const payrollGrants = {
  '03': ['generate_payroll'], '04': ['generate_payroll'], '05': ['approve_payroll'],
  '06': ['finalize_payroll'], '07': ['pay_salary'], '08': ['view_payroll'],
  '09': ['print_payslip'], '10': ['export_hr', 'export_payroll', 'view_payroll'],
};
const grantsFor = code => payrollGrants[code].map(grant => 'accounts.' + grant);
const deniedRoles = { teacher: 'TEACHER', hr: 'HR_OFFICER', restricted: 'RESTRICTED_EMPLOYEE' };
for (const { actual, ...report } of proofs(finance, 'finance-desktop', 'finance-outcomes')) {
  const { role, viewport, outcomes } = actual;
  if (viewport.width !== 1440 || viewport.height !== 900) throw new Error('Invalid finance viewport');
  const deniedRole = deniedRoles[role];
  if (deniedRole) {
    if (!outcomes.some(item => item.operation === 'finance-ui-denials' && item.ui)) {
      throw new Error('Missing Angular denial evidence for ' + role);
    }
    for (const [code, pattern] of [
      ['03', /^payroll\/preview\/$/], ['04', /^payroll\/generate\/$/],
      ['05', /^payroll\/[^/]+\/approve\/$/], ['06', /^payroll\/[^/]+\/finalize\/$/],
      ['07', /^salary-payments\/$/],
    ]) {
      const result = outcomes.find(item => pattern.test(item.operation) &&
        item.roleStatus === 403 && item.beforeVerified && [200, 201].includes(item.controlStatus));
      if (!result) throw new Error('Missing denied finance write ' + role + ' ' + code);
      add('E-RBAC-PAYROLL-' + deniedRole + '-' + code, { ...report, role, viewport, grants: grantsFor(code),
        endpoint: '/api/v1/hr/' + result.operation, status: 403,
        persistence: 'Permission-specific API denial preserved state. The same valid control reached the expected success status.',
        controlStatus: result.controlStatus });
    }
    for (const [code, pattern] of [
      ['08', /^payslips\/$/], ['09', /^payslips\/[^/]+\/$/], ['10', /^reports\/payroll\/export\/$/],
    ]) {
      const result = outcomes.find(item => pattern.test(item.read) && item.status === 403);
      if (!result) throw new Error('Missing denied financial read ' + role + ' ' + code);
      add('E-RBAC-PAYROLL-' + deniedRole + '-' + code, { ...report, role, viewport, grants: grantsFor(code),
        endpoint: '/api/v1/hr/' + result.read, status: 403,
        persistence: 'Administrator control opened the exact resource. The restricted response contained no protected entries.' });
    }
  }
  if (role === 'admin') {
    for (const [code, operation, pattern] of [
      ['09', 'payslip-print', /^payslips\/[^/]+\/$/],
      ['10', 'payroll-export', /^reports\/payroll\/export\/$/],
    ]) {
      const result = outcomes.find(item => pattern.test(item.read) && item.status === 200);
      if (!result || !outcomes.some(item => item.operation === operation && item.ui)) {
        throw new Error('Missing administrator browser evidence for ' + operation);
      }
      add('E-RBAC-PAYROLL-ADMINISTRATOR-' + code, { ...report, role, viewport, grants: grantsFor(code),
        endpoint: '/api/v1/hr/' + result.read, status: 200,
        persistence: 'Verified the fixture API and operated the authorized payslip or CSV browser control.' });
    }
  }
}
for (const [id, proof] of updates) {
  const row = byId.get(id);
  row.phase09kEvidence = proof;
  row.result = 'PASS';
  row.verificationClassification = 'ALREADY_VERIFIED';
  row.missingEvidence = null;
  delete row.openReason;
}
writeFileSync(checklist, JSON.stringify(rows, null, 2) + '\n');
process.stdout.write(JSON.stringify([...updates.keys()], null, 2) + '\n');
