import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const data = fixture.finance;
const mode = process.env.SMS_PHASE09_FINANCE;
const api = '/api/v1/hr/';
const amount = '1234.56';
const controlHeaders = { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf };

for (const [role, account] of Object.entries(fixture.accounts)) {
  if (mode === 'mobile' && role !== 'payroll') continue;
  test('finance access and transaction controls for ' + role, async ({ page, request }, info) => {
    await signIn(page, account);
    const grants = new Set(fixture.permissions[role]);
    const has = grant => grants.has('accounts.' + grant);
    const roleHeaders = { 'X-CSRFToken': (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token };
    const controlGet = endpoint => request.get(api + endpoint, { headers: controlHeaders });
    const controlPost = (endpoint, body) => request.post(api + endpoint, { headers: controlHeaders, data: body });
    const ownPost = (endpoint, body) => page.request.post(api + endpoint, { headers: roleHeaders, data: body });
    const outcomes = [];
    const reads = [
      ['salary-structures/', ['view_salary_setup']], ['salary-structures/' + data.structure + '/', ['view_salary_setup']],
      ['salary-assignments/', ['view_salary_setup']], ['salary-assignments/' + data.assignment + '/', ['view_salary_setup']],
      ['periods/', ['view_payroll']], ['payroll/', ['view_payroll']],
      ['payroll/' + data.run + '/', ['view_payroll']], ['salary-payments/', ['view_payroll']],
      ['salary-payments/' + data.payment + '/', ['view_payroll']], ['advances/', ['view_salary_setup']],
      ['advances/' + data.advance + '/', ['view_salary_setup']], ['payslips/', ['view_payroll']],
      ['payslips/' + data.entry + '/', ['print_payslip']],
      ['employees/' + data.employee + '/payslips/', ['view_payroll']],
      ['reports/payroll/', ['view_staff', 'view_payroll']],
      ['reports/payroll/export/', ['export_hr', 'export_payroll', 'view_payroll']],
    ];
    for (const [endpoint, required] of reads) {
      expect((await controlGet(endpoint)).status(), endpoint + ' control').toBe(200);
      const response = await page.request.get(api + endpoint);
      const expected = required.every(has) ? 200 : 403;
      expect(response.status(), endpoint).toBe(expected);
      if (expected === 403) {
        const body = await response.text();
        expect(body).not.toContain(amount);
        expect(JSON.parse(body)).not.toHaveProperty('results');
        expect(JSON.parse(body)).not.toHaveProperty('entries');
      }
      outcomes.push({ read: endpoint, status: expected });
    }

    if (has('view_salary_setup')) {
      await page.goto('/hr/salary-structures');
      await expect(page.getByRole('cell', { name: 'Finance fixture', exact: true })).toBeVisible();
      outcomes.push({ operation: 'salary-structures-view', ui: true });
    }
    if (has('view_payroll')) {
      await page.goto('/hr/payslips');
      await expect(page.getByRole('row').filter({ hasText: 'Fixture control' }).getByRole('cell', { name: 'Financial fixture', exact: true })).toBeVisible();
      outcomes.push({ operation: 'payslips-view', ui: true });
    }
    const period = data.periods[role];
    const runs = async () => (await (await controlGet('payroll/?period=' + period)).json()).results;
    const runDetail = async id => await (await controlGet('payroll/' + id + '/')).json();
    async function operation(endpoint, body, grant, status, snapshot, ui = false) {
      const before = await snapshot();
      if (!has(grant)) {
        const denied = await ownPost(endpoint, body);
        expect(denied.status(), endpoint).toBe(403);
        expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
        expect(await snapshot(), endpoint + ' preserved state').toEqual(before);
      }
      const response = ui && has(grant)
        ? await ui()
        : has(grant) ? await ownPost(endpoint, body) : await controlPost(endpoint, body);
      expect(response.status(), endpoint + ' allowed control').toBe(status);
      outcomes.push({ operation: endpoint, actor: role, roleStatus: has(grant) ? status : 403,
        controlStatus: status, ui: Boolean(ui && has(grant)), beforeVerified: true });
      return await response.json();
    }
    async function clickAction(label, endpoint) {
      const pending = page.waitForResponse(response => response.url().endsWith(api + endpoint)
        && response.request().method() === 'POST');
      await page.getByRole('button', { name: label, exact: true }).click();
      await page.getByRole('button', { name: 'Confirm', exact: true }).click();
      return pending;
    }
    const assignmentDate = new Date(fixture.day + 'T12:00:00Z');
    assignmentDate.setUTCDate(assignmentDate.getUTCDate() + Object.keys(fixture.accounts).indexOf(role) + 1);
    const assignmentPayload = {
      employee: data.employee, structure: data.structure,
      start_date: assignmentDate.toISOString().slice(0, 10), end_date: assignmentDate.toISOString().slice(0, 10),
    };
    const assignments = async () => (await (await controlGet('salary-assignments/?employee=' + data.employee)).json()).results;
    await page.goto('/hr/salary-assignments');
    if (!has('view_salary_setup')) await expect(page).toHaveURL(/\/access-denied$/);
    const assignment = await operation('salary-assignments/', assignmentPayload, 'manage_salary_setup', 201,
      assignments, has('view_salary_setup') && (async () => {
        await page.locator('#employee').selectOption(data.employee);
        await page.locator('#structure').selectOption(data.structure);
        await page.locator('#start_date').fill(assignmentPayload.start_date);
        await page.locator('#end_date').fill(assignmentPayload.end_date);
        const saved = page.waitForResponse(response => response.url().endsWith(api + 'salary-assignments/')
          && response.request().method() === 'POST');
        await page.getByRole('button', { name: 'Save record', exact: true }).click();
        return saved;
      }));
    expect((await assignments()).some(row => row.id === assignment.id &&
      row.start_date === assignmentPayload.start_date)).toBe(true);
    const financeForm = has('generate_payroll') && has('view_payroll');
    if (financeForm) {
      await page.goto('/hr/payroll');
      await page.locator('#period').selectOption(period);
    }
    await operation('payroll/preview/', { period }, 'generate_payroll', 200, runs, financeForm && (async () => {
      const response = page.waitForResponse(item => item.url().endsWith(api + 'payroll/preview/'));
      await page.getByRole('button', { name: 'Preview payroll', exact: true }).click();
      return response;
    }));
    expect(await runs()).toHaveLength(0);
    const generated = await operation('payroll/generate/', { period, key: crypto.randomUUID() },
      'generate_payroll', 201, runs, financeForm && (() => clickAction('Generate draft payroll', 'payroll/generate/')));
    expect(await runs()).toHaveLength(1);
    const endpoint = 'payroll/' + generated.id + '/';
    for (const [step, status] of [['submit', 'submitted'], ['review', 'reviewed'],
      ['approve', 'approved'], ['finalize', 'finalized']]) {
      let ui = false;
      if (has('view_payroll')) {
        await page.goto('/hr/payroll/' + generated.id);
        await expect(page.getByText('Financial fixture', { exact: true })).toBeVisible();
        const label = step[0].toUpperCase() + step.slice(1) + ' payroll';
        const action = page.getByRole('button', { name: label, exact: true });
        await expect(action).toHaveCount(has(step + '_payroll') ? 1 : 0);
        ui = () => clickAction(label, endpoint + step + '/');
      }
      await operation(endpoint + step + '/', {}, step + '_payroll', 200,
        async () => (await runDetail(generated.id)).status, ui);
      expect((await runDetail(generated.id)).status).toBe(status);
    }
    const balance = async () => (await runDetail(generated.id)).entries.results[0].outstanding;
    const entry = (await runDetail(generated.id)).entries.results[0];
    expect(await balance()).toBe(amount);
    const payload = { entry: entry.id, amount: '100.00', date: fixture.day, method: 'cash', key: crypto.randomUUID() };
    const payment = await operation('salary-payments/', payload, 'pay_salary', 201, balance);
    expect(await balance()).toBe('1134.56');
    const retry = await controlPost('salary-payments/', payload);
    expect(retry.status()).toBe(200);
    expect((await retry.json()).id).toBe(payment.id);
    expect(await balance()).toBe('1134.56');
    await operation('salary-payments/' + payment.id + '/reverse/', { reason: 'Fixture reversal' },
      'correct_payroll', 200, balance);
    expect(await balance()).toBe(amount);
    await operation('payroll-adjustments/', {
      entry: entry.id, amount: '-10.00', reason: 'Fixture adjustment', key: crypto.randomUUID(),
    }, 'correct_payroll', 201, balance);
    expect(await balance()).toBe('1224.56');
    expect((await controlPost(endpoint + 'recalculate/', {})).status()).toBe(409);
    expect(await balance()).toBe('1224.56');

    if (has('pay_salary') && has('view_payroll')) {
      await page.goto('/hr/payroll/' + generated.id);
      await page.getByRole('link', { name: 'Record payment' }).click();
      await expect(page.locator('#entry')).toHaveValue(entry.id);
      await page.locator('#amount').fill('25.00');
      await page.locator('#date').fill(fixture.day);
      const recorded = page.waitForResponse(response => response.url().endsWith(api + 'salary-payments/')
        && response.request().method() === 'POST');
      await page.getByRole('button', { name: 'Save record', exact: true }).click();
      await page.getByRole('button', { name: 'Confirm', exact: true }).click();
      const result = await recorded;
      expect(result.status()).toBe(201);
      expect(await balance()).toBe('1199.56');
      const post = await result.json();
      expect((await controlPost('salary-payments/' + post.id + '/reverse/', { reason: 'Fixture UI reversal' })).status()).toBe(200);
      expect(await balance()).toBe('1224.56');
      outcomes.push({ operation: 'salary-payments/', roleStatus: 201, ui: true, amountReconciled: true });
    }
    for (const [id, actions] of [
      [generated.id, ['HR_PAYROLL_GENERATED', 'HR_PAYROLL_APPROVED', 'HR_PAYROLL_FINALIZED']],
      [payment.id, ['HR_SALARY_PAYMENT_RECORDED', 'HR_SALARY_PAYMENT_REVERSED']],
    ]) {
      const audit = await request.get('/api/v1/audit/', { headers: controlHeaders, params: { search: id } });
      expect(audit.status()).toBe(200);
      const names = (await audit.json()).results.map(event => event.action);
      expect(names).toEqual(expect.arrayContaining(actions));
    }
    if (role === 'payroll' || role === 'admin') {
      await page.goto('/hr/payroll/' + generated.id);
      const print = page.getByRole('link', { name: 'Print payslip' });
      await expect(print).toBeVisible();
      const printable = page.waitForEvent('popup');
      await print.click();
      await expect((await printable).getByRole('heading', { name: 'Salary payslip' })).toBeVisible();
      expect(await page.evaluate(() => innerWidth)).toBe(mode === 'mobile' ? 390 : 1440);
      outcomes.push({ operation: 'payslip-print', ui: true });
      await page.goto('/hr/reports');
      await page.locator('select').filter({ has: page.locator('option[value=payroll]') }).selectOption('payroll');
      const csv = page.waitForEvent('download');
      await page.getByRole('link', { name: 'CSV export', exact: true }).click();
      expect((await csv).suggestedFilename()).toContain('payroll');
      outcomes.push({ operation: 'payroll-export', ui: true });
    }
    if (!has('view_payroll')) {
      for (const route of ['payroll', 'payroll/' + generated.id, 'payslips', 'salary-payments']) {
        await page.goto('/hr/' + route);
        await expect(page).toHaveURL(/\/access-denied$/);
      }
      await page.goto('/hr/reports');
      if (has('view_staff')) {
        await page.locator('select').filter({ has: page.locator('option[value=payroll]') }).selectOption('payroll');
        await expect(page.getByRole('link', { name: 'CSV export', exact: true })).toHaveCount(0);
      } else await expect(page).toHaveURL(/\/access-denied$/);
      outcomes.push({ operation: 'finance-ui-denials', ui: true });
    }
    if (role === 'payroll') {
      const changed = await request.put('/api/v1/roles/' + data.payrollRole + '/permissions/', {
        headers: controlHeaders,
        data: { permissions: [...grants].filter(grant => ![
          'accounts.pay_salary', 'accounts.view_payroll', 'accounts.print_payslip', 'accounts.export_payroll',
          ...(mode === 'desktop' ? ['accounts.manage_salary_setup', 'accounts.view_salary_setup',
            'accounts.generate_payroll', 'accounts.submit_payroll', 'accounts.review_payroll', 'accounts.approve_payroll',
            'accounts.finalize_payroll', 'accounts.correct_payroll'] : []),
        ].includes(grant)) },
      });
      expect(changed.status()).toBe(200);
      const unpaid = { ...payload, key: crypto.randomUUID() };
      expect((await ownPost('salary-payments/', unpaid)).status()).toBe(403);
      expect(await balance()).toBe('1224.56');
      for (const path of [endpoint, 'payslips/' + entry.id + '/', 'reports/payroll/export/']) {
        expect((await page.request.get(api + path)).status()).toBe(403);
      }
      await page.goto('/hr/payroll/' + generated.id);
      await expect(page).toHaveURL(/\/access-denied$/);
      await expect(page.getByText(amount, { exact: false })).toHaveCount(0);
      await page.goto('/hr/reports');
      const report = page.locator('select').filter({ has: page.locator('option[value=payroll]') });
      await report.selectOption('payroll');
      await expect(page.getByRole('link', { name: 'CSV export', exact: true })).toHaveCount(0);
      await report.selectOption('employees');
      await expect(page.getByRole('link', { name: 'CSV export', exact: true })).toBeVisible();
      outcomes.push({ operation: 'live payroll revocation', status: 403, balanceUnchanged: true });
      if (mode === 'desktop') {
        const periodResponse = await controlPost('periods/', {
          name: 'Live revocation period', start_date: fixture.day, end_date: fixture.day, separate_approver: false,
        });
        expect(periodResponse.status()).toBe(201);
        const period = (await periodResponse.json()).id;
        const lookup = async path => (await (await controlGet(path)).json());
        async function revokeWrite(path, body, snapshot, status) {
          const before = await snapshot();
          const denied = await ownPost(path, body);
          expect(denied.status(), path).toBe(403);
          const details = await denied.json();
          expect(details.details.detail).toMatch(/do not have permission/i);
          expect(await snapshot()).toEqual(before);
          const allowed = await controlPost(path, body);
          expect(allowed.status(), path + ' control').toBe(status);
          outcomes.push({ operation: 'revoked ' + path, status: 403, unchanged: true, controlStatus: status });
          return allowed.json();
        }
        const emptyRuns = () => lookup('payroll/?period=' + period);
        const generation = { period, key: crypto.randomUUID() };
        await revokeWrite('payroll/preview/', { period }, emptyRuns, 200);
        const run = await revokeWrite('payroll/generate/', generation, emptyRuns, 201);
        const runPath = 'payroll/' + run.id + '/';
        for (const [action, state] of [['submit', 'submitted'], ['review', 'reviewed'],
          ['approve', 'approved'], ['finalize', 'finalized']]) {
          await revokeWrite(runPath + action + '/', {}, () => runDetail(run.id), 200);
          expect((await runDetail(run.id)).status).toBe(state);
        }
        await revokeWrite('salary-payments/' + data.payment + '/reverse/', { reason: 'Isolated reversal' },
          () => lookup('salary-payments/' + data.payment + '/'), 200);
        await revokeWrite('payroll-adjustments/', {
          entry: entry.id, amount: '-5.00', reason: 'Isolated adjustment', key: crypto.randomUUID(),
        }, () => runDetail(generated.id), 201);
        await revokeWrite('advances/' + data.advance + '/disburse/', {},
          () => lookup('advances/' + data.advance + '/'), 200);
        await page.goto('/hr/advances');
        await expect(page).toHaveURL(/\/access-denied$/);
      }
      expect((await request.put('/api/v1/roles/' + data.payrollRole + '/permissions/', {
        headers: controlHeaders, data: { permissions: [...grants] },
      })).status()).toBe(200);
      await page.goto('/hr/payroll');
      await expect(page.getByRole('button', { name: 'Preview payroll', exact: true })).toBeVisible();
    }
    await info.attach('finance-outcomes', {
      body: JSON.stringify({ role, viewport: page.viewportSize(), outcomes }), contentType: 'application/json',
    });
  });
}
