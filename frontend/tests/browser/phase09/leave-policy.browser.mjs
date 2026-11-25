import { readFileSync, writeFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const hr = '/api/v1/hr/';

test('E-LEAVE-11 schedules a policy revision and preserves posted credits and consumption', async ({ page, browser }, info) => {
  test.setTimeout(90000);
  await signIn(page, fixture.accounts.admin);
  async function action(path, button, confirm = false) {
    const pending = page.waitForResponse(response =>
      response.url().endsWith(hr + path) && response.request().method() === 'POST');
    await button.click();
    if (confirm) await page.getByRole('button', { name: 'Confirm', exact: true }).click();
    return pending;
  }
  const save = path => action(path, page.getByRole('button', { name: 'Save record', exact: true }));
  await page.goto('/hr/employees/new');
  await page.locator('#first_name').fill('Revision employee');
  await page.locator('#department').selectOption(fixture.employeeFields.department);
  await page.locator('#designation').selectOption(fixture.employeeFields.designation);
  await page.locator('#employment_type').fill('Contract');
  await page.locator('#joined_on').fill('2025-01-01');
  const employeeResult = await save('employees/');
  expect(employeeResult.status()).toBe(201);
  const employee = (await employeeResult.json()).id;

  await page.goto('/hr/contracts');
  await page.locator('#employee').selectOption(employee);
  await page.locator('#kind').fill('Leave version fixture contract');
  await page.locator('#start_date').fill('2025-01-01');
  await page.locator('#end_date').fill('2025-12-31');
  await page.locator('#weekdays').fill('0,1,2,3,4');
  expect((await save('contracts/')).status()).toBe(201);

  const name = 'Versioned paid leave';
  await page.goto('/hr/leave-types');
  await page.locator('#name').fill(name);
  await page.locator('#code').fill('VERSIONED');
  await page.locator('#annual_days').fill('12');
  await page.locator('#accrual_mode').selectOption('monthly');
  const policyResult = await save('leave-types/');
  expect(policyResult.status()).toBe(201);
  const policy = (await policyResult.json()).id;
  const versionPath = 'leave-types/' + policy + '/versions/';
  const versions = async () => {
    const response = await page.request.get(hr + versionPath);
    expect(response.status()).toBe(200);
    return response.json();
  };
  const [initial] = await versions();
  expect(initial.status).toBe('effective');
  async function ledger(through, preview = false) {
    const response = await page.request.get(hr + 'leave-balances/', {
      params: {employee, leave_type: policy, through, ...(preview ? {preview: '1'} : {})},
    });
    expect(response.status()).toBe(200);
    return response.json();
  }
  async function balanceForm(through, method, value) {
    await page.goto('/hr/leaves');
    const panel = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Leave balance and accrual' }),
    });
    await panel.getByLabel('Employee ID').fill(employee);
    await panel.getByLabel('Leave type ID').fill(policy);
    await panel.getByLabel('Process through').fill(through);
    await panel.getByLabel('Action').selectOption(method);
    await panel.getByRole('button', { name: 'Run selected action' }).click();
    await expect(panel.getByText(new RegExp('Posted balance ' + value + '(\\.0+)? days'))).toBeVisible();
    return panel;
  }
  await balanceForm('2025-06-30', 'apply', '6');
  const credited = await ledger('2025-06-30');
  expect(credited.ledger).toHaveLength(6);
  expect(credited.ledger.every(row => row.amount === '1.00' && row.policy_version === initial.id)).toBe(true);

  await page.locator('#employee').selectOption(employee);
  await page.locator('#leave_type').selectOption(policy);
  await page.locator('#start_date').fill('2025-06-30');
  await page.locator('#end_date').fill('2025-06-30');
  await page.locator('#reason').fill('Historical consumption fixture');
  const submitted = await save('leaves/');
  expect(submitted.status()).toBe(201);
  const leave = (await submitted.json()).id;
  const leaveRow = page.getByRole('row').filter({ hasText: 'Historical consumption fixture' });
  expect((await action('leaves/' + leave + '/approve/', leaveRow.getByRole('button', {name:'Approve', exact:true}), true)).status()).toBe(200);
  const original = await ledger('2025-06-30');
  expect(Number(original.balance)).toBe(5);
  expect(original.ledger).toEqual(expect.arrayContaining(credited.ledger));
  expect(original.ledger).toContainEqual(expect.objectContaining({event:'consumption', amount:'-1.00', leave}));

  await page.goto('/hr/leave-types');
  const row = page.getByRole('row').filter({hasText: name});
  await row.getByRole('button', {name:'Policy versions', exact:true}).click();
  const history = page.getByRole('list', {name:'Leave policy version history'});
  await expect(history).toContainText('12 annual days');
  await page.getByRole('button', {name:'Schedule revision', exact:true}).click();
  await page.getByLabel('Effective date', {exact:true}).fill('2025-07-01');
  await page.locator('#revision-annual_days').fill('24');
  await page.locator('#revision-carry_limit').fill('4');
  await expect(page.getByText('Proposed entitlement 24 days from 2025-07-01.')).toBeVisible();
  expect((await action(versionPath, page.getByRole('button', {name:'Save revision', exact:true}))).status()).toBe(201);
  await expect(history).toContainText('scheduled');
  await expect(history).toContainText('24 annual days');
  const [revision] = await versions();
  expect(revision.effective_start).toBe('2025-07-01');

  const before = await balanceForm('2025-06-30', 'preview', '5');
  await expect(before.getByText('Applied policy entitlement 12 days · Version ' + initial.id)).toBeVisible();
  const future = await balanceForm('2025-07-31', 'preview', '5');
  await expect(future.getByText('Applied policy entitlement 24 days · Version ' + revision.id)).toBeVisible();
  const projection = await ledger('2025-07-31', true);
  expect(projection.preview).toEqual([expect.objectContaining({
    event:'accrual', amount:2, policy_version_id:revision.id,
  })]);

  const unauthorized = await browser.newContext({baseURL: process.env.SMS_PHASE09_BASE_URL});
  try {
    const outsider = await unauthorized.newPage();
    await signIn(outsider, fixture.accounts.hr);
    await outsider.goto('/hr/leave-types');
    await outsider.getByRole('row').filter({hasText:name}).getByRole('button', {name:'Policy versions', exact:true}).click();
    await expect(outsider.getByRole('list', {name:'Leave policy version history'})).toContainText('24 annual days');
    await expect(outsider.getByRole('button', {name:'Schedule revision', exact:true})).toHaveCount(0);
    const csrf = await (await outsider.request.get('/api/v1/auth/csrf/')).json();
    const rejected = await outsider.request.post(hr + versionPath, {
      headers:{'X-CSRFToken':csrf.csrf_token},
      data:{effective_start:'2025-08-01', terms:{annual_days:36}},
    });
    expect(rejected.status()).toBe(403);
    expect((await rejected.json()).details.detail).toMatch(/do not have permission/i);
    expect(await versions()).toEqual([revision, expect.objectContaining({id:initial.id})]);
  } finally {
    await unauthorized.close();
  }

  writeFileSync(process.env.SMS_PHASE09_LEAVE_CLOCK, '2025-07-31\n');
  await balanceForm('2025-07-31', 'apply', '7');
  const final = await ledger('2025-07-31');
  expect(final.ledger).toEqual(expect.arrayContaining(original.ledger));
  expect(final.ledger).toHaveLength(8);
  expect(await ledger('2025-06-30')).toEqual(original);
  expect(final.ledger.at(-1)).toEqual(expect.objectContaining({
    effective_date:'2025-07-31', amount:'2.00', policy_version:revision.id,
  }));
  expect(Number(final.balance)).toBe(final.ledger.reduce((total, entry) => total + Number(entry.amount), 0));
  await balanceForm('2025-07-31', 'apply', '7');
  expect((await ledger('2025-07-31')).ledger).toEqual(final.ledger);
  await page.goto('/hr/leave-types');
  await page.getByRole('row').filter({hasText:name}).getByRole('button', {name:'Policy versions', exact:true}).click();
  await expect(history).toContainText('historical');
  await expect(history).toContainText('effective');
  const width = info.project.name === 'leave-mobile' ? 390 : 1440;
  expect(await page.evaluate(() => innerWidth)).toBe(width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await info.attach('leave-policy-outcome', {contentType:'application/json', body:JSON.stringify({
    id:'E-LEAVE-11', viewport:page.viewportSize(), policy, initial:initial.id, revision:revision.id,
    priorCredits:6, preservedConsumption:1, revisedCredit:2, reconciledBalance:7,
    deniedStatus:403, duplicatePost:false,
  })});
});
