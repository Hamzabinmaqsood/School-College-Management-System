import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const target = fixture.teacherWrite;

test('teacher exam writes and live attendance and marks grant revocation', async ({ page, request }, info) => {
  await signIn(page, fixture.accounts.teacher);
  const control = { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf };
  const csrf = { 'X-CSRFToken': (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token };
  const path = '/api/v1/examinations/marks/' + target.draft + '/';
  const assignment = '/api/v1/attendance/assignments/' + fixture.examAssignment + '/';
  const role = '/api/v1/roles/' + target.role + '/permissions/';
  const all = fixture.permissions.teacher;
  const audit = [];
  const state = async () => {
    const result = await request.get(path, { headers: control });
    expect(result.status()).toBe(200);
    return await result.json();
  };
  const saveBody = (version, obtained) => ({
    version, marks: [{ registration: target.registration, status: 'marked', obtained }],
  });
  const offset = (days) => {
    const now = new Date(fixture.day + 'T12:00:00Z');
    now.setUTCDate(now.getUTCDate() + days);
    return now.toISOString().slice(0, 10);
  };
  await page.goto('/examinations/marks');
  await page.getByRole('row').filter({ hasText: 'Scope fixtures' }).getByRole('button', { name: 'Open', exact: true }).click();
  const mark = page.locator('input[aria-label^="Marks for"]');
  await mark.fill('54');
  const saved = page.waitForResponse(response => response.url().endsWith(path + 'save/'));
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  expect((await saved).status()).toBe(200);
  expect((await state()).marks[0].obtained).toBe('54.00');

  try {
    for (const [label, fields] of [
      ['future', { effective_start: offset(1), effective_end: offset(2) }],
      ['expired', { effective_start: offset(-2), effective_end: offset(-1) }],
      ['inactive', { active: false, effective_start: fixture.day, effective_end: fixture.day }],
    ]) {
      expect((await request.patch(assignment, { headers: control, data: fields })).status()).toBe(200);
      const before = await state();
      const payload = saveBody(before.version, '56.00');
      const denied = await page.request.post(path + 'save/', { headers: csrf, data: payload });
      expect(denied.status(), label).toBe(404);
      expect(await state()).toEqual(before);
      const permitted = await request.post(path + 'save/', { headers: control, data: payload });
      expect(permitted.status(), label + ' control').toBe(200);
      expect((await state()).marks[0].obtained).toBe('56.00');
      audit.push({ scenario: label, denied: 404, allowed: 200, unchanged: true });
    }
  } finally {
    expect((await request.patch(assignment, { headers: control, data: {
      active: true, effective_start: fixture.day, effective_end: fixture.day,
    } })).status()).toBe(200);
  }
  for (const [scenario, resource] of Object.entries(target.unrelated)) {
    const endpoint = '/api/v1/examinations/marks/' + resource.submission + '/';
    const read = async () => {
      const controlRead = await request.get(endpoint, { headers: control });
      expect(controlRead.status()).toBe(200);
      return await controlRead.json();
    };
    const before = await read();
    const write = { version: before.version, marks: [
      { registration: resource.registration, status: 'marked', obtained: '30.00' },
    ] };
    const denied = await page.request.post(endpoint + 'save/', { data: write, headers: csrf });
    expect(denied.status(), scenario).toBe(404);
    expect(await read()).toEqual(before);
    const allowed = await request.post(endpoint + 'save/', { data: write, headers: control });
    expect(allowed.status(), scenario + ' control').toBe(200);
    expect((await read()).marks[0].obtained).toBe('30.00');
    audit.push({ scenario, denied: 404, allowed: 200, unchanged: true });
  }
  const register = '/api/v1/attendance/';
  const attendance = fixture.attendance;
  const entry = await page.request.post(register, { headers: csrf, data: attendance });
  expect(entry.status()).toBe(201);
  const revise = removed => request.put(role, {
    headers: control, data: { permissions: all.filter(code => !removed.includes(code)) },
  });
  const next = { ...attendance, period: 'P10' };
  const roster = async () => (await (await request.get(register + 'roster/', {
    headers: control, params: next,
  })).json()).register;
  try {
    expect((await revise(['attendance.add_attendancesession', 'accounts.update_exam_marks',
      'accounts.submit_exam_marks'])).status()).toBe(200);
    const before = await state();
    for (const [action, data] of [
      ['save/', saveBody(before.version, '65.00')], ['submit/', { version: before.version }],
    ]) {
      const denied = await page.request.post(path + action, { headers: csrf, data });
      expect(denied.status()).toBe(403);
      expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
      expect(await state()).toEqual(before);
    }
    expect(await roster()).toBeNull();
    const denied = await page.request.post(register, { headers: csrf, data: next });
    expect(denied.status()).toBe(403);
    expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
    expect(await roster()).toBeNull();

    await page.goto('/examinations/marks');
    await page.getByRole('row').filter({ hasText: 'Scope fixtures' }).getByRole('button', { name: 'Open', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Assessment roster' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Submit for verification', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save draft', exact: true })).toHaveCount(0);

    await page.goto('/attendance');
    const group = page.getByLabel('Teaching group');
    const option = group.locator('option').filter({ hasText: /Acceptance Section.*Acceptance Subject/ });
    await expect(option).toHaveCount(1);
    await group.selectOption(await option.getAttribute('value'));
    await page.locator('input[type=date]').fill(fixture.day);
    await page.getByPlaceholder('e.g. P1').fill('P10');
    await page.getByRole('button', { name: 'Load roster', exact: true }).click();
    await expect(page.getByText(/read-only access/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start draft', exact: true })).toHaveCount(0);
    await page.goto('/attendance/history');
    await expect(page.getByRole('heading', { name: 'Attendance history' })).toBeVisible();
    audit.push({ scenario: 'teacher grant revocation', denied: 403, unchanged: true,
      attendanceReadOnly: true, historicalRoute: true });
  } finally {
    expect((await revise([])).status()).toBe(200);
  }

  const regained = await page.request.post(register, { headers: csrf, data: next });
  expect(regained.status()).toBe(201);
  expect((await roster()).id).toBe((await regained.json()).id);
  await page.goto('/examinations/marks');
  await page.getByRole('row').filter({ hasText: 'Scope fixtures' }).getByRole('button', { name: 'Open', exact: true }).click();
  const submitted = page.waitForResponse(response => response.url().endsWith(path + 'submit/'));
  await page.getByRole('button', { name: 'Submit for verification', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  expect((await submitted).status()).toBe(200);
  expect((await state()).status).toBe('submitted');
  await info.attach('teacher-write-outcomes', { body: JSON.stringify(audit), contentType: 'application/json' });
});
