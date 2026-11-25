import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES, 'utf8'));
const resources = [
  { endpoint: 'employees/', grant: 'view_staff', route: 'employees', label: 'Employees' },
  { endpoint: 'employees/' + fixture.employee + '/', grant: 'view_staff' },
  { endpoint: 'attendance/', grant: 'view_staff_attendance', route: 'attendance', label: 'Staff attendance' },
  { endpoint: 'attendance/calendar/?employee=' + fixture.employee, grant: 'view_staff_attendance' },
  { endpoint: 'leaves/', grant: 'view_staff_leave', route: 'leaves', label: 'Employee leave' },
  { endpoint: 'salary-structures/', grant: 'view_salary_setup', route: 'salary-structures', label: 'Salary structures' },
  { endpoint: 'overtime/', grant: 'view_payroll', route: 'overtime', label: 'Overtime requests' },
  { endpoint: 'payroll/', grant: 'view_payroll', route: 'payroll', label: 'Payroll' },
  { endpoint: 'documents/' + fixture.document + '/download/', grant: 'view_employee_documents' },
];

async function employeeWrites(page, request, role, grants, outcomes) {
  const headers = { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf };
  const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json();
  const ownHeaders = { 'X-CSRFToken': csrf.csrf_token };
  const base = '/api/v1/hr/employees/';
  const profile = base + fixture.writeTargets[role] + '/';
  const data = { ...fixture.employeeFields, code: 'CREATE-' + role, first_name: 'Created' };
  const search = async () => {
    const response = await request.get(base, { headers, params: { search: data.code } });
    expect(response.status()).toBe(200);
    return (await response.json()).results;
  };
  const readProfile = async () => {
    const response = await request.get(profile, { headers });
    expect(response.status()).toBe(200);
    return await response.json();
  };
  const canCreate = grants.has('accounts.add_employee');
  const canEdit = grants.has('accounts.change_employee');
  await expect.poll(search).toHaveLength(0);
  await page.goto('/hr/employees/new');
  if (canCreate) {
    for (const [key, value] of Object.entries(data)) {
      const field = page.locator('#' + key);
      if (['department', 'designation'].includes(key)) await field.selectOption(value);
      else await field.fill(value);
    }
    const result = page.waitForResponse(response => response.url().endsWith(base) &&
      response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Save record', exact: true }).click();
    expect((await result).status()).toBe(201);
  } else {
    await expect(page).toHaveURL(/\/access-denied$/);
    const denied = await page.request.post(base, { headers: ownHeaders, data });
    expect(denied.status()).toBe(403);
    expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
    expect(await search()).toHaveLength(0);
    expect((await request.post(base, { headers, data })).status()).toBe(201);
  }
  const created = await search();
  expect(created).toHaveLength(1);
  expect(created[0].first_name).toBe('Created');
  outcomes.push({ operation: 'employee-create', status: canCreate ? 201 : 403, verifiedPersistence: true });

  expect((await readProfile()).first_name).toBe('Prior');
  await page.goto('/hr/employees/' + fixture.writeTargets[role]);
  const edit = page.getByRole('button', { name: 'Edit employee', exact: true });
  if (canEdit) {
    await edit.click();
    await page.locator('#first_name').fill('Revised');
    const result = page.waitForResponse(response => response.url().endsWith(profile) &&
      response.request().method() === 'PATCH');
    await page.getByRole('button', { name: 'Save record', exact: true }).click();
    expect((await result).status()).toBe(200);
  } else {
    if (grants.has('accounts.view_staff')) {
      await expect(page.getByRole('heading', { name: 'Employee profile' })).toBeVisible();
      await expect(edit).toHaveCount(0);
    } else {
      await expect(page).toHaveURL(/\/access-denied$/);
    }
    const patch = { first_name: 'Revised' };
    const denied = await page.request.patch(profile, { headers: ownHeaders, data: patch });
    expect(denied.status()).toBe(403);
    expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
    expect((await readProfile()).first_name).toBe('Prior');
    expect((await request.patch(profile, { headers, data: patch })).status()).toBe(200);
  }
  expect((await readProfile()).first_name).toBe('Revised');
  outcomes.push({ operation: 'employee-edit', status: canEdit ? 200 : 403, verifiedPersistence: true });
}

for (const [role, account] of Object.entries(fixture.accounts)) {
  test('five-role read matrix for ' + role, async ({ page, request }, info) => {
    await signIn(page, account);
    const grants = new Set(fixture.permissions[role]);
    const outcomes = [];
    for (const resource of resources) {
      const expected = grants.has('accounts.' + resource.grant) ? 200 : 403;
      const reply = await page.request.get('/api/v1/hr/' + resource.endpoint);
      expect(reply.status(), role + ' ' + resource.endpoint).toBe(expected);
      if (expected === 403) {
        const error = await reply.json();
        expect(error.code).toBeDefined();
        expect(error).not.toHaveProperty('results');
        expect(error).not.toHaveProperty('snapshot');
      }
      if (resource.endpoint === 'employees/' + fixture.employee + '/' && expected === 200 &&
          !grants.has('accounts.view_payroll')) {
        const profile = await reply.json();
        for (const field of ['salary', 'gross', 'net', 'payroll', 'salary_history']) {
          expect(profile).not.toHaveProperty(field);
        }
      }
      outcomes.push({ endpoint: resource.endpoint, expected, actual: reply.status() });
    }
    for (const resource of resources.filter(item => item.route)) {
      await page.goto('/hr/' + resource.route);
      const permitted = grants.has('accounts.' + resource.grant);
      if (permitted) {
        await expect(page.getByRole('heading', { name: resource.label, exact: true })).toBeVisible();
        const nav = page.getByRole('navigation', { name: 'Human resources' });
        for (const item of resources.filter(entry => entry.route)) {
          await expect(nav.getByRole('link', { name: item.label, exact: true })).toHaveCount(
            grants.has('accounts.' + item.grant) ? 1 : 0,
          );
        }
      } else {
        await expect(page).toHaveURL(/\/access-denied$/);
      }
    }
    await employeeWrites(page, request, role, grants, outcomes);
    if (role === 'hr') {
      const roleUpdate = await request.put('/api/v1/roles/' + fixture.hrRole + '/permissions/', {
        data: { permissions: [...grants].filter(grant => !['accounts.view_staff', 'accounts.change_employee'].includes(grant)) },
        headers: { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf },
      });
      expect(roleUpdate.status()).toBe(200);
      const denied = await page.request.get('/api/v1/hr/employees/');
      expect(denied.status()).toBe(403);
      expect(await denied.json()).not.toHaveProperty('results');
      const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json();
      const endpoint = '/api/v1/hr/employees/' + fixture.writeTargets[role] + '/';
      const editDenied = await page.request.patch(endpoint, {
        headers: { 'X-CSRFToken': csrf.csrf_token }, data: { first_name: 'After revocation' },
      });
      expect(editDenied.status()).toBe(403);
      expect((await editDenied.json()).details.detail).toMatch(/do not have permission/i);
      const control = await request.get(endpoint, { headers: { Cookie: fixture.control.cookie } });
      expect((await control.json()).first_name).toBe('Revised');
      outcomes.push({ operation: 'employee-edit-revoked', status: 403, verifiedPersistence: true });
      await page.goto('/hr/employees');
      await expect(page).toHaveURL(/\/access-denied$/);
      await page.goto('/hr/leaves');
      const nav = page.getByRole('navigation', { name: 'Human resources' });
      await expect(nav.getByRole('link', { name: 'Employees', exact: true })).toHaveCount(0);
      outcomes.push({ endpoint: 'employees/ after revocation', expected: 403, actual: denied.status() });
    }
    await info.attach('role-outcomes', {
      body: JSON.stringify({ role, viewport: page.viewportSize(), outcomes }),
      contentType: 'application/json',
    });
  });
}
