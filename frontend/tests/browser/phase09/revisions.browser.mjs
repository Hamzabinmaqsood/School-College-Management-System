import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const control = { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf };
const structures = '/api/v1/hr/salary-structures/';
const mode = process.env.SMS_PHASE09_REVISIONS;

async function saveForm(page, path, method) {
  const response = page.waitForResponse(item => item.url().endsWith(path) && item.request().method() === method);
  await page.getByRole('button', { name: path.startsWith(structures) ? 'Save draft' : 'Save record', exact: true }).click();
  return response;
}

for (const [role, account] of Object.entries(fixture.accounts)) {
  if (mode === 'mobile' && role !== 'admin') continue;
  test('salary draft revisions and permissions for ' + role, async ({ page, request }, info) => {
    test.setTimeout(65000);
    await signIn(page, account);
    const granted = new Set(fixture.permissions[role]);
    const mayView = granted.has('accounts.view_salary_setup');
    const manages = granted.has('accounts.manage_salary_setup');
    const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json();
    const own = { 'X-CSRFToken': csrf.csrf_token };
    const name = 'Revision fixture ' + role;
    const code = 'REV-' + role;
    const payload = { name, code, basic: '1234.56', active: false, basis: 'monthly',
      components: [{ label: 'Allowance', kind: 'earning', amount: '17.25' }] };
    const rows = async () => (await (await request.get(structures, { headers: control, params: { search: code } })).json()).results;
    await page.goto('/hr/salary-structures');
    if (manages) {
      await page.locator('#name').fill(name);
      await page.locator('#code').fill(code);
      await page.locator('#basic').fill('1234.56');
      await page.getByRole('button', { name: 'Add component' }).click();
      await page.locator('[formcontrolname=label]').fill('Allowance');
      await page.locator('[formcontrolname=amount]').fill('17.25');
      expect((await saveForm(page, structures, 'POST')).status()).toBe(201);
    } else {
      await expect(page).toHaveURL(/\/access-denied$/);
      const denied = await page.request.post(structures, { data: payload, headers: own });
      expect(denied.status()).toBe(403);
      expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
      expect(await rows()).toHaveLength(0);
      expect((await request.post(structures, { data: payload, headers: control })).status()).toBe(201);
    }
    const [created] = await rows();
    expect(created.basic).toBe('1234.56');
    expect(created.components[0].amount).toBe('17.25');
    const endpoint = structures + created.id + '/';
    const roleView = await page.request.get(endpoint);
    expect(roleView.status()).toBe(mayView ? 200 : 403);
    if (mayView) {
      expect((await roleView.json()).id).toBe(created.id);
      await expect(page.getByRole('row').filter({ hasText: name })).toBeVisible();
    } else {
      const denial = await roleView.text();
      expect(JSON.parse(denial).details.detail).toMatch(/do not have permission/i);
      expect(denial).not.toContain(name);
      expect(denial).not.toContain(payload.basic);
    }
    const read = async () => (await (await request.get(endpoint, { headers: control })).json());
    if (manages) {
      await page.getByRole('row').filter({ hasText: name }).getByRole('button', { name: 'Edit', exact: true }).click();
      await expect(page.locator('[formcontrolname=label]')).toHaveValue('Allowance');
      await page.getByRole('button', { name: 'Add component' }).click();
      await page.locator('[formcontrolname=label]').nth(1).fill('Deduction');
      await page.locator('[formcontrolname=kind]').nth(1).selectOption('deduction');
      await page.locator('[formcontrolname=amount]').nth(1).fill('2.30');
      expect((await saveForm(page, endpoint, 'PATCH')).status()).toBe(200);
    } else {
      const before = await read();
      const data = { components: [...payload.components,
        { label: 'Deduction', kind: 'deduction', amount: '2.30' }] };
      const denied = await page.request.patch(endpoint, { data, headers: own });
      expect(denied.status()).toBe(403);
      expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
      expect(await read()).toEqual(before);
      expect((await request.patch(endpoint, { data, headers: control })).status()).toBe(200);
    }
    const opened = await request.post(endpoint + 'submit/', { data: {}, headers: control });
    expect(opened.status()).toBe(201);
    const approval = (await opened.json()).id;
    const reviewer = { Cookie: fixture.salaryReviewer.cookie, 'X-CSRFToken': fixture.salaryReviewer.csrf };
    expect((await request.post(endpoint + 'approve/', { data: { approval }, headers: reviewer })).status()).toBe(200);
    expect((await request.post(endpoint + 'activate/', { data: { approval }, headers: control })).status()).toBe(200);
    const active = await read();
    expect(active.active).toBe(true);
    expect(active.components.map(item => item.amount).sort()).toEqual(['17.25', '2.30']);
    expect((await request.patch(endpoint, { data: { basic: '9.00' }, headers: control })).status()).toBe(400);
    expect(await read()).toEqual(active);
    const audit = await request.get('/api/v1/audit/', {
      headers: control, params: { search: created.id },
    });
    expect(audit.ok()).toBe(true);
    const events = (await audit.json()).results.filter(item => item.resource_id === created.id);
    const actor = manages ? account.username : fixture.accounts.admin.username;
    expect(events.map(item => [item.action, item.actor]).sort()).toEqual([
      ['HR_CREATED', actor], ['HR_SALARY_STRUCTURE_ACTIVATED', fixture.accounts.admin.username],
      ['HR_SALARY_STRUCTURE_APPROVED', fixture.salaryReviewer.username],
      ['HR_SALARY_STRUCTURE_SUBMITTED', fixture.accounts.admin.username], ['HR_UPDATED', actor],
    ]);
    if (role === 'admin' && mode === 'mobile') {
      await verifyLeave(page, request);
      await verifyRetention(page, request);
      await verifyCalendar(page);
    }
    if (role === 'payroll') await verifySalaryRevocation(page, request, granted, own);
    await info.attach('revision-outcomes', { body: JSON.stringify({
      role, viewport: page.viewportSize(), structure: { allowed: manages, mayView, activeProtected: true, audited: true },
      mobileLeave: role === 'admin' && mode === 'mobile',
      mobileRetention: role === 'admin' && mode === 'mobile',
      mobileCalendar: role === 'admin' && mode === 'mobile',
      salaryRevocation: role === 'payroll',
    }), contentType: 'application/json' });
  });
}

async function verifyLeave(page, request) {
  const { employee, year } = fixture.revisionLeave;
  const policy = '/api/v1/hr/leave-types/';
  const ledger = '/api/v1/hr/leave-balances/';
  const name = 'Mobile carry policy';
  await page.goto('/hr/leave-types');
  await page.locator('#name').fill(name);
  await page.locator('#code').fill('CARRY-UI');
  await page.locator('#annual_days').fill('0');
  await page.locator('#accrual_mode').selectOption('manual');
  await page.locator('#carry_limit').fill('3');
  await page.locator('#carry_expiry_days').fill('30');
  const response = await saveForm(page, policy, 'POST');
  expect(response.status()).toBe(201);
  const created = await response.json();
  expect(Number(created.carry_limit)).toBe(3);
  expect(created.carry_expiry_days).toBe(30);
  await page.goto('/hr/leaves');
  const form = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Leave balance and accrual' }) });
  await form.getByLabel('Employee ID').fill(employee);
  await form.getByLabel('Leave type ID').fill(created.id);
  const through = form.getByLabel('Process through');
  const action = form.locator('select');
  const run = form.getByRole('button', { name: 'Run selected action', exact: true });
  const opening = (year - 1) + '-12-31';
  async function post(when, operation, expectedBalance, url) {
    await through.fill(when);
    await action.selectOption(operation);
    const response = page.waitForResponse(item => item.url().endsWith(ledger + url) && item.request().method() === 'POST');
    await run.click();
    expect((await response).ok()).toBe(true);
    await expect(form.getByText(new RegExp('Posted balance ' + expectedBalance + '(\\.0+)? days'))).toBeVisible();
  }
  await form.getByLabel('Signed adjustment amount').fill('5.00');
  await form.getByLabel('Adjustment reason').fill('Fixture opening');
  await post(opening, 'opening', '5', 'adjust/');
  await post(year + '-01-05', 'apply', '3', 'apply/');
  const snapshot = async date => (await (await request.get(ledger, {
    headers: control, params: { employee, leave_type: created.id, through: date },
  })).json());
  const carry = await snapshot(year + '-01-05');
  expect(carry.ledger.map(row => [row.event, row.amount])).toEqual([['carry', '3.00']]);
  const original = await snapshot(opening);
  await post(year + '-02-01', 'apply', '0', 'apply/');
  const expired = await snapshot(year + '-02-01');
  expect(expired.ledger.map(row => [row.event, row.amount])).toEqual([
    ['carry', '3.00'], ['expiration', '-3.00'],
  ]);
  await post(year + '-02-01', 'apply', '0', 'apply/');
  expect((await snapshot(year + '-02-01')).ledger).toEqual(expired.ledger);
  expect((await snapshot(opening)).ledger).toEqual(original.ledger);
  await page.goto('/hr/leave-types');
  await page.locator('#name').fill('Mobile monthly policy');
  await page.locator('#code').fill('MONTH-UI');
  await page.locator('#annual_days').fill('12');
  await page.locator('#accrual_mode').selectOption('monthly');
  await page.locator('#prorate').uncheck();
  const added = await saveForm(page, policy, 'POST');
  expect(added.status()).toBe(201);
  const monthly = (await added.json()).id;
  await page.goto('/hr/leaves');
  await form.getByLabel('Employee ID').fill(employee);
  await form.getByLabel('Leave type ID').fill(monthly);
  const march = year + '-03-01';
  const monthlySnapshot = async () => (await (await request.get(ledger, {
    headers: control, params: { employee, leave_type: monthly, through: march },
  })).json()).ledger;
  await post(march, 'apply', '5', 'apply/');
  const accrued = await monthlySnapshot();
  expect(accrued.map(row => [row.event, row.amount])).toEqual([
    ['accrual', '1.00'], ['accrual', '4.00'],
  ]);
  await post(march, 'apply', '5', 'apply/');
  expect(await monthlySnapshot()).toEqual(accrued);
  expect(await page.evaluate(() => innerWidth)).toBe(390);
}

async function verifyCalendar(page) {
  const { employee, year } = fixture.revisionLeave;
  const month = year + '-02';
  await page.goto('/hr/attendance/calendar');
  await page.locator('#calendar-employee').fill(employee);
  await page.locator('#calendar-month').fill(month);
  await page.getByRole('button', { name: 'Show calendar', exact: true }).click();
  const day = number => page.locator('.attendance-calendar li').filter({
    has: page.getByText(month + '-' + number, { exact: true }),
  });
  await expect(day('01')).toContainText(/Present\s+·\s+22:00(?::00)? to 06:00(?::00)? next day/i);
  await expect(day('01')).toContainText('Check-in 22:10');
  await expect(day('01')).toContainText('Check-out 05:45');
  await expect(day('02')).toContainText(/ · Absent/i);
  await expect(day('03')).toContainText(/ · Leave/i);
  await expect(day('04')).toContainText(/ · Unrecorded/i);
}

async function verifyRetention(page, request) {
  const endpoint = '/api/v1/hr/documents/' + fixture.document + '/';
  const download = async () => {
    const response = await request.get(endpoint + 'download/', { headers: control });
    expect(response.status()).toBe(200);
    return await response.body();
  };
  const original = await download();
  await page.goto('/hr/documents/due');
  const due = page.getByRole('row').filter({ hasText: 'Acceptance due scan' });
  await expect(due).toBeVisible();
  await due.getByRole('link', { name: 'Employee documents', exact: true }).click();
  const document = page.getByText('Acceptance due scan', { exact: false });
  await expect(document).toContainText('contract');
  await expect(document).toContainText('Review ' + fixture.day);
  const form = page.locator('form').filter({
    has: page.getByRole('button', { name: 'Record decision', exact: true }),
  });
  const revised = new Date(fixture.day + 'T12:00:00Z');
  revised.setUTCDate(revised.getUTCDate() + 40);
  const date = revised.toISOString().slice(0, 10);
  async function decide(action, reason) {
    await form.locator('select').selectOption(action);
    await form.getByLabel('Reason').fill(reason);
    const saved = page.waitForResponse(item => item.url().endsWith(endpoint + 'retention/'));
    await form.getByRole('button', { name: 'Record decision', exact: true }).click();
    expect((await saved).status()).toBe(200);
  }
  await form.getByLabel('New review date for extension').fill(date);
  await decide('extend', 'Mobile decision extended');
  await expect(document).toContainText(date);
  await decide('hold', 'Mobile hold');
  await expect(document).toContainText('On hold');
  await expect(document.getByRole('button', { name: 'Archive', exact: true })).toHaveCount(0);
  await decide('release', 'Mobile release');
  await expect(document).not.toContainText('On hold');
  await document.getByRole('button', { name: 'Archive', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(document).toContainText('Archived');
  await document.getByRole('button', { name: 'Review history', exact: true }).click();
  await expect(page.getByText(/extend.*Mobile decision extended/)).toBeVisible();
  await expect(page.getByText(/hold.*Mobile hold/)).toBeVisible();
  await expect(page.getByText(/release.*Mobile release/)).toBeVisible();
  expect(await download()).toEqual(original);
  await page.goto('/hr/settings');
  await page.locator('#document_retention_by_kind').fill('{"contract":180}');
  expect((await saveForm(page, '/api/v1/hr/settings/', 'PATCH')).status()).toBe(200);
  const persisted = await request.get(endpoint, { headers: control });
  expect(persisted.status()).toBe(200);
  const row = await persisted.json();
  expect(row.review_on).toBe(date);
  expect(row.archived_at).toBeTruthy();
}

async function verifySalaryRevocation(page, request, grants, own) {
  const draft = { name: 'Revocation draft', code: 'REVOKE-BEFORE', basic: '100.00',
    active: false, basis: 'monthly', components: [] };
  const created = await page.request.post(structures, { data: draft, headers: own });
  expect(created.status()).toBe(201);
  const path = structures + (await created.json()).id + '/';
  const before = await page.request.patch(path, { data: { basic: '101.00' }, headers: own });
  expect(before.status()).toBe(200);
  const end = new Date(fixture.day + 'T12:00:00Z');
  end.setUTCDate(end.getUTCDate() + 1);
  const date = end.toISOString().slice(0, 10);
  const assignments = '/api/v1/hr/salary-assignments/';
  const assignment = { employee: fixture.finance.employee, structure: fixture.finance.structure,
    start_date: date, end_date: date };
  const inserted = await page.request.post(assignments, { data: assignment, headers: own });
  expect(inserted.status()).toBe(201);
  end.setUTCDate(end.getUTCDate() + 1);
  const following = end.toISOString().slice(0, 10);
  assignment.start_date = following;
  assignment.end_date = following;
  const salaryRole = '/api/v1/roles/' + fixture.finance.payrollRole + '/permissions/';
  const set = permissions => request.put(salaryRole, { headers: control, data: { permissions } });
  try {
    expect((await set([...grants].filter(grant => grant !== 'accounts.manage_salary_setup'))).status()).toBe(200);
    const planned = { ...draft, code: 'REVOKE-AFTER' };
    const actions = [
      ['POST', structures, planned],
      ['PATCH', path, { basic: '102.00' }],
      ['POST', assignments, assignment],
    ];
    for (const [method, url, data] of actions) {
      const denied = await page.request.fetch(url, { method, headers: own, data });
      expect(denied.status()).toBe(403);
      expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
    }
    const known = await request.get(path, { headers: control });
    expect((await known.json()).basic).toBe('101.00');
    const list = await request.get(structures, { headers: control, params: { search: planned.code } });
    expect((await list.json()).results).toHaveLength(0);
    const assigned = await request.get(assignments, { headers: control, params: { employee: assignment.employee } });
    expect((await assigned.json()).results.some(item => item.start_date === following)).toBe(false);
    await page.goto('/hr/salary-structures');
    await expect(page.getByRole('row').filter({ hasText: draft.name })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save draft', exact: true })).toHaveCount(0);
    expect((await request.post(structures, { data: planned, headers: control })).status()).toBe(201);
    expect((await request.patch(path, { data: { basic: '102.00' }, headers: control })).status()).toBe(200);
    expect((await request.post(assignments, { data: assignment, headers: control })).status()).toBe(201);
  } finally {
    expect((await set([...grants])).status()).toBe(200);
  }
}
