import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES, 'utf8'));


test('E-CAL-01 and E-DOC-05 correction history and due-document actions', async ({ page }, info) => {
  await signIn(page, fixture.accounts.admin);
  expect(await page.evaluate(() => innerWidth)).toBe(info.project.name === 'mobile' ? 390 : 1440);
  await page.goto('/hr/attendance/calendar');
  const record = page.getByRole('row').filter({ hasText: fixture.day });
  await expect(record).toHaveCount(1);
  const relevant = record.getByRole('button', { name: 'Correct attendance', exact: true });
  await expect(relevant).toBeDisabled();
  const old = (await record.getByRole('cell').allTextContents()).map(text => text.trim()).find(text => ['present', 'late', 'excused'].includes(text));
  expect(old).toBeDefined();
  const revised = old === 'late' ? 'excused' : 'late';
  await page.getByLabel('Decision or correction reason').fill('Acceptance correction ' + info.project.name);
  await page.getByLabel('Corrected status').selectOption(revised);
  await relevant.click();
  const correction = page.waitForResponse(response => response.url().endsWith('/correct/'));
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  expect((await correction).status()).toBe(200);
  await record.getByRole('button', { name: 'Correction history' }).click();
  await expect(page.getByRole('heading', { name: 'Attendance correction history' })).toBeVisible();
  await expect(page.getByText('Previous status: ' + old + ' · Revised status: ' + revised)).toBeVisible();

  await page.goto('/hr/documents/due');
  const due = page.getByRole('row').filter({ hasText: 'Acceptance due scan' });
  await expect(due.getByRole('link', { name: 'Download due document' })).toHaveAttribute(
    'href', '/api/v1/hr/documents/' + fixture.document + '/download/',
  );
  const response = page.waitForResponse(item => item.url().endsWith('/' + fixture.document + '/download/'));
  const download = page.waitForEvent('download');
  await due.getByRole('link', { name: 'Download due document' }).click();
  expect((await response).status()).toBe(200);
  const file = await download;
  const png = readFileSync(await file.path());
  await due.getByRole('link', { name: 'Employee documents' }).click();
  await expect(page).toHaveURL(new RegExp('/hr/employees/' + fixture.employee + '$'));
  await expect(page.getByText('Acceptance due scan')).toBeVisible();

  await page.goto('/hr/settings');
  await page.getByLabel('Retention days by document type (JSON)').fill('{"contract":30}');
  await page.getByRole('button', { name: 'Save record', exact: true }).click();
  await expect(page.getByText('Record saved.', { exact: true })).toBeVisible();
  await page.goto('/hr/employees/' + fixture.employee);
  const panel = page.locator('section').filter({
    has: page.getByRole('heading', { name: 'Private employee documents' }),
  });
  const label = 'Policy-derived scan ' + info.project.name;
  await panel.getByLabel('Label', { exact: true }).fill(label);
  await panel.getByLabel('Document category').fill('contract');
  await panel.getByLabel('Document scan').setInputFiles({ name: 'fixture.png', mimeType: 'image/png', buffer: png });
  await panel.getByRole('button', { name: 'Upload' }).click();
  const deadline = new Date(fixture.day + 'T12:00:00Z');
  deadline.setUTCDate(deadline.getUTCDate() + 30);
  await expect(panel.getByText(label, { exact: false })).toContainText('Review ' + deadline.toISOString().slice(0, 10));
});

test('E-DOC-13 restricted account cannot download the exact document', async ({ page }, info) => {
  test.skip(info.project.name === 'mobile', 'The same server authorization is exercised on desktop.');
  await signIn(page, fixture.accounts.restricted);
  const result = await page.request.get('/api/v1/hr/documents/' + fixture.document + '/download/');
  expect(result.status()).toBe(403);
  expect(result.headers()['content-type']).toContain('application/json');
  const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json();
  for (const endpoint of ['attendance/' + fixture.staffAttendance + '/correct/', 'leave-balances/adjust/']) {
    const response = await page.request.post('/api/v1/hr/' + endpoint, {
      data: {}, headers: { 'X-CSRFToken': csrf.csrf_token },
    });
    expect(response.status(), endpoint).toBe(403);
  }
});

test('E-ROLE-01 HR employee profile excludes payroll data', async ({ page }, info) => {
  test.skip(info.project.name === 'mobile', 'The same serialization is exercised on desktop.');
  await signIn(page, fixture.accounts.hr);
  await page.goto('/hr/employees/' + fixture.employee);
  await expect(page.getByRole('heading', { name: 'Employee profile' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Salary history' })).toHaveCount(0);
  const response = await page.request.get('/api/v1/hr/employees/' + fixture.employee + '/');
  expect(response.status()).toBe(200);
  const body = await response.json();
  for (const key of ['salary', 'gross', 'net', 'payroll', 'salary_history']) {
    expect(body).not.toHaveProperty(key);
  }
});

test('E-ATT-02 to E-ATT-10 teacher attendance scope and operational denials', async ({ page, request }, info) => {
  test.skip(info.project.name === 'mobile', 'Authorization and teaching-group coverage run on desktop.');
  await signIn(page, fixture.accounts.teacher);
  await page.goto('/attendance');
  const group = page.getByLabel('Teaching group');
  await expect(group.locator('option').filter({ hasText: /Acceptance Section.*Acceptance Subject/ })).toHaveCount(1);
  await expect(group.locator('option').filter({ hasText: /Unrelated|Future|Expired|Inactive/ })).toHaveCount(0);
  const assigned = fixture.attendance;
  const roster = data => page.request.get('/api/v1/attendance/roster/', { params: data });
  expect((await roster(assigned)).status()).toBe(200);
  expect((await roster({ ...assigned, academic_class: fixture.unrelated.class, section: '' })).status()).toBe(403);
  expect((await roster({ ...assigned, section: fixture.unrelated.section })).status()).toBe(403);
  expect((await roster({ ...assigned, subject: fixture.unrelated.subject })).status()).toBe(403);

  for (const offset of [-1, 1]) {
    const date = new Date(assigned.date + 'T12:00:00Z');
    date.setUTCDate(date.getUTCDate() + offset);
    expect((await roster({ ...assigned, date: date.toISOString().slice(0, 10) })).status()).toBe(403);
  }
  const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json();
  for (const state of ['future', 'expired', 'inactive']) {
    const response = await page.request.post('/api/v1/attendance/', {
      data: { ...assigned, section: fixture.unrelated[state] },
      headers: { 'X-CSRFToken': csrf.csrf_token },
    });
    expect(response.status(), state).toBe(403);
  }

  await page.goto('/students/' + fixture.student);
  await page.getByRole('button', { name: 'Attendance', exact: true }).click();
  const filter = page.getByRole('button', { name: 'Apply filters', exact: true });
  await expect(filter).toBeEnabled();
  await page.locator('select[name=mode]').selectOption('period');
  await filter.click();
  await expect(page.getByText(/1 eligible sessions.*Present 1/)).toBeVisible();
  await expect(page.getByRole('region', { name: 'Attendance report results' }).getByText('present', { exact: true })).toBeVisible();

  await page.goto('/examinations/marks');
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Assessment roster' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Verify marks', exact: true })).toHaveCount(0);
  for (const [path, data] of [
    ['marks/' + fixture.marks + '/verify/', {}],
    ['results/' + fixture.result + '/approve/', {}],
    ['results/' + fixture.result + '/publish/', { confirmed: true }],
  ]) {
    const response = await page.request.post('/api/v1/examinations/' + path, {
      data, headers: { 'X-CSRFToken': csrf.csrf_token },
    });
    expect(response.status(), path).toBe(403);
  }
  const control = { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf };
  const marksEndpoint = id => '/api/v1/examinations/marks/' + id + '/';
  const outcomes = [];
  for (const [name, id] of Object.entries(fixture.examScope)) {
    expect((await request.get(marksEndpoint(id), { headers: control })).status()).toBe(200);
    const denied = await page.request.get(marksEndpoint(id));
    expect(denied.status(), name).toBe(404);
    expect(await denied.json()).not.toHaveProperty('marks');
    outcomes.push({ name, id, allowed: 200, denied: 404 });
  }
  const assignmentEndpoint = '/api/v1/attendance/assignments/' + fixture.examAssignment + '/';
  const dateOffset = offset => {
    const d = new Date(fixture.day + 'T12:00:00Z');
    d.setUTCDate(d.getUTCDate() + offset);
    return d.toISOString().slice(0, 10);
  };
  try {
    for (const [name, data] of [
      ['future', { effective_start: dateOffset(1), effective_end: dateOffset(2) }],
      ['expired', { effective_start: dateOffset(-2), effective_end: dateOffset(-1) }],
      ['inactive', { active: false, effective_start: fixture.day, effective_end: fixture.day }],
    ]) {
      expect((await request.patch(assignmentEndpoint, { headers: control, data })).status()).toBe(200);
      expect((await request.get(marksEndpoint(fixture.marks), { headers: control })).status()).toBe(200);
      expect((await page.request.get(marksEndpoint(fixture.marks))).status(), name).toBe(404);
      outcomes.push({ name, id: fixture.marks, allowed: 200, denied: 404 });
    }
  } finally {
    const data = { active: true, effective_start: fixture.day, effective_end: fixture.day };
    expect((await request.patch(assignmentEndpoint, { headers: control, data })).status()).toBe(200);
  }
  expect((await page.request.get(marksEndpoint(fixture.marks))).status()).toBe(200);
  await info.attach('exam-scope', {
    body: JSON.stringify(outcomes), contentType: 'application/json',
  });
  const approved = await request.post('/api/v1/examinations/results/' + fixture.result + '/approve/', {
    data: {},
    headers: { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf },
  });
  expect(approved.status()).toBe(200);
  const published = await request.post('/api/v1/examinations/results/' + fixture.result + '/publish/', {
    data: { confirmed: true },
    headers: { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf },
  });
  expect(published.status()).toBe(200);
});
