import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const files = process.argv.slice(2);
if (files.length !== 2) throw new Error('Provide the desktop and mobile Playwright report paths.');
const checklist = new URL('./checklist.json', import.meta.url);
const rows = JSON.parse(readFileSync(checklist));
const row = rows.find(item => item.id === 'E-LEAVE-11');
if (rows.length !== 211 || new Set(rows.map(item => item.id)).size !== 211 || !row) {
  throw new Error('Unexpected checklist identity.');
}
function specs(suite) {
  return [...(suite.specs ?? []), ...(suite.suites ?? []).flatMap(specs)];
}

const evidence = files.map((file, index) => {
  const project = index === 0 ? 'leave-desktop' : 'leave-mobile';
  const candidates = specs(JSON.parse(readFileSync(file)))
    .filter(spec => spec.title.startsWith('E-LEAVE-11 '))
    .flatMap(spec => spec.tests.filter(test => test.projectName === project)
      .map(test => ({ name: spec.title, result: test.results.at(-1) })));
  const { name, result } = candidates.length === 1 ? candidates[0] : {};
  const attachment = result?.attachments.find(item => item.name === 'leave-policy-outcome');
  if (result?.status !== 'passed' || !attachment?.body) throw new Error('No passing evidence for ' + project);
  const outcome = JSON.parse(Buffer.from(attachment.body, 'base64'));
  const [width, height] = index === 0 ? [1440, 900] : [390, 844];
  if (outcome.id !== row.id || outcome.viewport.width !== width || outcome.viewport.height !== height
      || !outcome.policy || !outcome.initial || !outcome.revision || outcome.initial === outcome.revision
      || outcome.priorCredits !== 6 || outcome.preservedConsumption !== 1 || outcome.revisedCredit !== 2
      || outcome.reconciledBalance !== 7 || outcome.deniedStatus !== 403 || outcome.duplicatePost !== false) {
    throw new Error('Incomplete evidence for ' + project);
  }
  return { artifact: resolve(file), test: name, project, outcome };
});

row.phase09lEvidence = {
  requirement: row.requirement, route: row.angularRoute, endpoint: row.backendEndpoint,
  expected: row.expected, role: 'Institution administrator and HR reader',
  type: ['Angular browser workflow', 'API authorization', 'Ledger reconciliation'],
  implementation: 'hr.0012_leave_policy_versions, hr/leave_policy.py, hr/accrual.py, hr/leave_balance.py',
  backendTests: [
    'test_leave_policy_revision_preserves_posted_terms',
    'test_version_history_read_only_when_license_expires',
    'test_concurrent_policy_publications_have_one_effective_version',
    'test_concurrent_leave_revision_and_accrual_keep_the_original_version',
    'test_scheduled_carry_revision_uses_january_terms_and_rolls_back_on_failure',
  ],
  evidence, result: 'PASS',
};
row.result = 'PASS';
row.verificationClassification = 'ALREADY_VERIFIED';
row.missingEvidence = null;
delete row.openReason;
writeFileSync(checklist, JSON.stringify(rows, null, 2) + '\n');
