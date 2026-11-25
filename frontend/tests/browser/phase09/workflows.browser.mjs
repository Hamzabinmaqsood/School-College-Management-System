import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const api = '/api/v1/hr/';
const control = { Cookie: fixture.control.cookie, 'X-CSRFToken': fixture.control.csrf };
const mobile = process.env.SMS_PHASE09_WORKFLOWS === 'mobile';
const names = { admin: 'ADMINISTRATOR', hr: 'HR_OFFICER', payroll: 'PAYROLL_OFFICER',
  teacher: 'TEACHER', restricted: 'RESTRICTED_EMPLOYEE' };

for (const [role, account] of Object.entries(fixture.accounts)) {
  if (mobile && role !== 'admin') continue;
  test('HR workflows for ' + role, async ({ page, request }, info) => {
    test.setTimeout(90000);
    await signIn(page, account);
    const grants = new Set(fixture.permissions[role]);
    const has = grant => grants.has('accounts.' + grant);
    const csrf = { 'X-CSRFToken': (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token };
    const target = fixture.workflow.roles[role];
    const person = fixture.writeTargets[role];
    const outcomes = [];
    const get = async path => {
      const response = await request.get(api + path, { headers: control });
      expect(response.status(), path).toBe(200);
      return response;
    };
    const state = async path => (await get(path)).json();
    function record(group, number, grant, endpoint, resource, status, persistence) {
      outcomes.push({ id: 'E-RBAC-' + group + '-' + names[role] + '-' + number,
        role, grant: 'accounts.' + grant, endpoint: api + endpoint, resource, status,
        persistence, viewport: page.viewportSize() });
    }
    async function open(route, heading, grant) {
      await page.goto('/hr/' + route);
      if (has(grant)) await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
      else await expect(page).toHaveURL(/\/access-denied$/);
    }
    async function denial(response) {
      expect(response.status()).toBe(403);
      const body = await response.json();
      expect(body.details.detail).toMatch(/do not have permission/i);
      expect(body).not.toHaveProperty('results');
      expect(body).not.toHaveProperty('snapshot');
    }
    async function read(path, grant, check) {
      const trusted = await get(path);
      const session = await page.request.get(api + path);
      if (has(grant)) {
        expect(session.status()).toBe(200);
        if (!path.includes('?')) expect(await session.body()).toEqual(await trusted.body());
        await check();
      } else await denial(session);
      return session.status();
    }
    async function write(path, grant, body, status, snapshot, ui) {
      const before = await snapshot();
      if (!has(grant)) {
        await denial(await page.request.post(api + path, { headers: csrf, data: body }));
        expect(await snapshot()).toEqual(before);
      }
      const response = has(grant) ? await ui()
        : await request.post(api + path, { headers: control, data: body });
      expect(response.status(), path).toBe(status);
      return { status: has(grant) ? status : 403, before };
    }
    async function action(path, button, confirm = false) {
      const saved = page.waitForResponse(response =>
        response.url().endsWith(api + path) && response.request().method() === 'POST');
      await button.click();
      if (confirm) await page.getByRole('button', { name: 'Confirm', exact: true }).click();
      return saved;
    }
    if (!mobile) {
      await open('employees', 'Employees', 'view_staff');
      let endpoint = 'employees/?search=EMP-1';
      let status = await read(endpoint, 'view_staff', async () => {
        await expect(page.getByRole('row').filter({ hasText: 'EMP-1' })).toBeVisible();
      });
      record('EMPLOYEES', '01', 'view_staff', endpoint, fixture.employee, status, 'Exact employee verified.');
      await open('employees/' + fixture.employee, 'Employee profile', 'view_staff');
      const panel = page.getByRole('heading', { name: 'Private employee documents' });
      if (!has('view_employee_documents')) await expect(panel).toHaveCount(0);
      endpoint = 'documents/?employee=' + fixture.employee;
      status = await read(endpoint, 'view_employee_documents', async () => {
        await expect(panel).toBeVisible();
        await expect(page.getByText('Acceptance due scan')).toBeVisible();
      });
      record('DOCUMENTS', '01', 'view_employee_documents', endpoint, fixture.document, status, 'Exact document metadata verified.');
      endpoint = 'documents/' + fixture.document + '/download/';
      status = await read(endpoint, 'view_employee_documents', async () => {
        const link = page.getByRole('link', { name: 'Download', exact: true });
        await expect(link).toHaveAttribute('href', api + endpoint);
        const downloaded = page.waitForEvent('download');
        await link.click();
        expect(readFileSync(await (await downloaded).path())).toEqual(await (await get(endpoint)).body());
      });
      record('DOCUMENTS', '02', 'view_employee_documents', endpoint, fixture.document, status, 'Exact stored file verified.');
      await open('attendance', 'Staff attendance', 'view_staff_attendance');
      endpoint = 'attendance/?employee=' + person;
      status = await read(endpoint, 'view_staff_attendance', async () => {
        await expect(page.getByRole('row').filter({ hasText: 'Correction target ' + role })).toBeVisible();
      });
      record('ATTENDANCE', '01', 'view_staff_attendance', endpoint, target.correction, status, 'Exact fixture listing verified.');
      await open('attendance/calendar', 'Staff attendance', 'view_staff_attendance');
      const month = fixture.day.slice(0, 7);
      endpoint = 'attendance/calendar/?employee=' + person + '&month=' + month;
      status = await read(endpoint, 'view_staff_attendance', async () => {
        await page.locator('#calendar-employee').fill(person);
        await page.locator('#calendar-month').fill(month);
        await page.getByRole('button', { name: 'Show calendar', exact: true }).click();
        const day = page.locator('.attendance-calendar li').filter({
          has: page.getByText(fixture.day, { exact: true }),
        });
        await expect(day).toContainText(/present/i);
      });
      record('ATTENDANCE', '04', 'view_staff_attendance', endpoint, person, status, 'Exact employee and date verified.');
      const mark = { employee: target.markTarget, date: fixture.day, status: 'present' };
      const marked = async () => (await state('attendance/?employee=' + target.markTarget)).results;
      if (!has('mark_staff_attendance')) await expect(page.locator('#employee')).toHaveCount(0);
      const created = await write('attendance/', 'mark_staff_attendance', mark, 201, marked, async () => {
        await page.locator('#employee').selectOption(mark.employee);
        await page.locator('#date').fill(mark.date);
        await page.locator('#status').selectOption(mark.status);
        return action('attendance/', page.getByRole('button', { name: 'Save record', exact: true }));
      });
      expect(created.before).toHaveLength(0);
      expect(await marked()).toEqual([expect.objectContaining(mark)]);
      record('ATTENDANCE', '02', 'mark_staff_attendance', 'attendance/', mark.employee, created.status, 'No row after denial. Verified the attendance row after the allowed write.');
      const row = page.getByRole('row').filter({ hasText: 'Correction target ' + role });
      const button = row.getByRole('button', { name: 'Correct attendance', exact: true });
      if (!has('correct_staff_attendance')) await expect(button).toHaveCount(0);
      const detail = 'attendance/' + target.correction + '/';
      const corrected = await write(detail + 'correct/', 'correct_staff_attendance',
        { reason: 'Fixture correction', status: 'late' }, 200,
        async () => [await state(detail), await state(detail + 'corrections/')], async () => {
          await page.getByLabel('Decision or correction reason').fill('Fixture correction');
          await page.getByLabel('Corrected status').selectOption('late');
          return action(detail + 'correct/', button, true);
        });
      expect((await state(detail)).status).toBe('late');
      if (has('correct_staff_attendance')) {
        await row.getByRole('button', { name: 'Correction history' }).click();
        await expect(page.getByText('Previous status: present · Revised status: late')).toBeVisible();
      }
      record('ATTENDANCE', '03', 'correct_staff_attendance', detail + 'correct/', target.correction,
        corrected.status, 'Checked the row and history after denial and revised status after the allowed write.');
      await open('leaves', 'Employee leave', 'view_staff_leave');
      endpoint = 'leaves/?employee=' + person;
      status = await read(endpoint, 'view_staff_leave', async () => {
        await expect(page.getByRole('row').filter({ hasText: 'Request target ' + role })).toBeVisible();
      });
      record('LEAVES', '01', 'view_staff_leave', endpoint, target.leave, status, 'Exact leave request verified.');
      const leave = 'leaves/' + target.leave + '/';
      const leaveRow = page.getByRole('row').filter({ hasText: 'Request target ' + role });
      const approveLeave = leaveRow.getByRole('button', { name: 'Approve', exact: true });
      if (!has('approve_staff_leave')) await expect(approveLeave).toHaveCount(0);
      const accepted = await write(leave + 'approve/', 'approve_staff_leave', {}, 200,
        () => state(leave), () => action(leave + 'approve/', approveLeave, true));
      expect(accepted.before.status).toBe('pending');
      expect((await state(leave)).status).toBe('approved');
      record('LEAVES', '03', 'approve_staff_leave', leave + 'approve/', target.leave,
        accepted.status, 'Verified the pending request before denial and approved status after the authorized decision.');

      const ledger = 'leave-balances/';
      const adjustment = { employee: person, leave_type: fixture.workflow.ledgerPolicy,
        through: fixture.day, kind: 'opening', amount: '3.00', reason: 'Fixture opening',
        key: crypto.randomUUID() };
      const balance = () => state(ledger + '?employee=' + person +
        '&leave_type=' + adjustment.leave_type + '&through=' + fixture.day);
      const adjustmentButton = page.getByRole('button', { name: 'Run selected action', exact: true });
      if (!has('approve_staff_leave')) await expect(page.locator('option[value=opening]')).toHaveCount(0);
      const adjusted = await write(ledger + 'adjust/', 'approve_staff_leave',
        adjustment, 201, balance, async () => {
          const panel = page.locator('section').filter({
            has: page.getByRole('heading', { name: 'Leave balance and accrual' }),
          });
          await panel.getByLabel('Employee ID').fill(person);
          await panel.getByLabel('Leave type ID').fill(adjustment.leave_type);
          await panel.getByLabel('Process through').fill(fixture.day);
          await panel.getByLabel('Signed adjustment amount').fill(adjustment.amount);
          await panel.getByLabel('Adjustment reason').fill(adjustment.reason);
          await panel.locator('select').selectOption('opening');
          return action(ledger + 'adjust/', adjustmentButton);
        });
      expect((await balance()).ledger).toEqual([
        expect.objectContaining({ event: 'opening', amount: '3.00' }),
      ]);
      record('LEAVES', '04', 'approve_staff_leave', ledger + 'adjust/', person,
        adjusted.status, 'Verified the ledger after denial and the exact opening transaction after the allowed write.');

      await open('leave-types', 'Leave types', 'view_staff_leave');
      const policy = { name: 'Workflow policy ' + role, code: 'WF-' + role, annual_days: 12 };
      const found = async () => (await state('leave-types/')).results.filter(row => row.code === policy.code);
      if (!has('manage_hr_registry')) await expect(page.locator('#name')).toHaveCount(0);
      const createdPolicy = await write('leave-types/', 'manage_hr_registry', policy, 201, found, async () => {
        await page.locator('#name').fill(policy.name);
        await page.locator('#code').fill(policy.code);
        await page.locator('#annual_days').fill(String(policy.annual_days));
        return action('leave-types/', page.getByRole('button', { name: 'Save record', exact: true }));
      });
      expect(createdPolicy.before).toHaveLength(0);
      const [createdRow] = await found();
      expect(createdRow).toEqual(expect.objectContaining({ name: policy.name, annual_days: 12 }));
      record('LEAVES', '05', 'manage_hr_registry', 'leave-types/', createdRow.id,
        createdPolicy.status, 'Verified no record after denial and exact saved policy after allowed creation.');

      await open('leaves', 'Employee leave', 'view_staff_leave');
      const day = new Date(fixture.day + 'T12:00:00Z');
      while ([0, 6].includes(day.getUTCDay())) day.setUTCDate(day.getUTCDate() + 1);
      const date = day.toISOString().slice(0, 10);
      const leaveRequest = { employee: target.markTarget, leave_type: fixture.workflow.leavePolicy,
        start_date: date, end_date: date, reason: 'Created leave ' + role };
      const requests = async () => (await state('leaves/?employee=' + target.markTarget)).results;
      if (!has('request_staff_leave')) await expect(page.locator('#start_date')).toHaveCount(0);
      const submitted = await write('leaves/', 'request_staff_leave', leaveRequest, 201, requests, async () => {
        await page.locator('#employee').selectOption(leaveRequest.employee);
        await page.locator('#leave_type').selectOption(leaveRequest.leave_type);
        await page.locator('#start_date').fill(date);
        await page.locator('#end_date').fill(date);
        await page.locator('#reason').fill(leaveRequest.reason);
        return action('leaves/', page.getByRole('button', { name: 'Save record', exact: true }));
      });
      expect(submitted.before).toHaveLength(0);
      const [pending] = await requests();
      expect(pending).toEqual(expect.objectContaining({ ...leaveRequest, status: 'pending' }));
      record('LEAVES', '02', 'request_staff_leave', 'leaves/', pending.id,
        submitted.status, 'Verified no new request after denial and the persisted pending request after the allowed write.');
    }
    await open('overtime', 'Overtime requests', 'view_payroll');
    const overtime = 'overtime/' + target.overtime + '/';
    const row = page.getByRole('row').filter({ hasText: target.correction });
    const status = await read(overtime, 'view_payroll', async () => {
      await expect(row).toBeVisible();
    });
    record('OVERTIME', '03', 'view_payroll', overtime, target.overtime, status, 'Exact overtime detail verified.');
    const approve = row.getByRole('button', { name: 'Approve', exact: true });
    if (!has('approve_payroll')) await expect(approve).toHaveCount(0);
    const decision = { status: 'approved', hours: '1.50', reason: 'Approved fixture overtime' };
    const result = await write(overtime + 'decision/', 'approve_payroll', decision, 200,
      () => state(overtime), async () => {
        await row.getByLabel('Approved hours').fill(decision.hours);
        await row.getByLabel('Overtime decision reason').fill(decision.reason);
        return action(overtime + 'decision/', approve, true);
      });
    const approved = await state(overtime);
    expect(result.before.status).toBe('pending');
    expect(approved.status).toBe('approved');
    expect(Number(approved.snapshot.hours)).toBe(1.5);
    record('OVERTIME', '02', 'approve_payroll', overtime + 'decision/', target.overtime,
      result.status, 'Pending state preserved on denial. Authorized approval persisted status and hours.');
    if (!mobile) {
      const [mark] = (await state('attendance/?employee=' + target.markTarget)).results;
      const overtimeRequest = { attendance: mark.id, policy: fixture.workflow.policy, requested_hours: '2.00' };
      const requests = async () => (await state('overtime/?attendance__employee=' + target.markTarget)).results;
      if (!has('generate_payroll')) await expect(page.locator('#attendance')).toHaveCount(0);
      const submitted = await write('overtime/', 'generate_payroll', overtimeRequest, 201, requests, async () => {
        await page.locator('#attendance').fill(mark.id);
        await page.locator('#policy').selectOption(overtimeRequest.policy);
        await page.locator('#requested_hours').fill(overtimeRequest.requested_hours);
        return action('overtime/', page.getByRole('button', { name: 'Save record', exact: true }));
      });
      expect(submitted.before).toHaveLength(0);
      const [pending] = await requests();
      expect(pending).toEqual(expect.objectContaining({ ...overtimeRequest, status: 'pending' }));
      record('OVERTIME', '01', 'generate_payroll', 'overtime/', pending.id,
        submitted.status, 'Verified no request after denial and exact persisted request after the allowed write.');

      if (role === 'payroll' && has('approve_payroll') && has('generate_payroll')) {
        const pendingPath = 'overtime/' + pending.id + '/';
        const before = await state(pendingPath);
        const ownDecision = await page.request.post(api + pendingPath + 'decision/', {
          headers: csrf, data: decision,
        });
        expect(ownDecision.status()).toBe(400);
        expect(JSON.stringify(await ownDecision.json())).toMatch(/different user/i);
        expect(await state(pendingPath)).toEqual(before);
        const reviewer = await request.post(api + pendingPath + 'decision/', { headers: control, data: decision });
        expect(reviewer.status()).toBe(200);
        const reviewed = await state(pendingPath);
        expect(reviewed.status).toBe('approved');
        await info.attach('separate-overtime', {
          body: JSON.stringify({ id: pending.id, selfApproval: 400, distinctApproval: 200 }),
          contentType: 'application/json',
        });
      }
      await open('overtime-policies', 'Overtime policies', 'view_payroll');
      const policy = { name: 'Overtime workflow ' + role, start_date: fixture.day, end_date: fixture.day,
        rate: '12.50', minimum_hours: '0', maximum_hours: '8', regular_multiplier: '1',
        rest_multiplier: '1', holiday_multiplier: '1', separate_approver: true };
      const policies = async () => (await state('overtime-policies/')).results.filter(row => row.name === policy.name);
      if (!has('generate_payroll')) await expect(page.locator('#name')).toHaveCount(0);
      const defined = await write('overtime-policies/', 'generate_payroll', policy, 201, policies, async () => {
        for (const [key, value] of Object.entries(policy)) {
          if (key !== 'separate_approver') await page.locator('#' + key).fill(value);
        }
        return action('overtime-policies/', page.getByRole('button', { name: 'Save record', exact: true }));
      });
      expect(defined.before).toHaveLength(0);
      const [savedPolicy] = await policies();
      expect(savedPolicy).toEqual(expect.objectContaining({
        name: policy.name, rate: policy.rate, separate_approver: true,
      }));
      record('OVERTIME', '04', 'generate_payroll', 'overtime-policies/', savedPolicy.id, defined.status,
        'Checked no policy after denial and read back its rate and separate-approver setting.');
    }
    if (mobile) outcomes.push({ id: 'E-MOB-07', role, grant: 'accounts.approve_payroll',
      endpoint: api + overtime + 'decision/', resource: target.overtime, status: result.status,
      persistence: 'Approved 1.50 hours from the 390 px Angular form and verified the persisted snapshot.',
      viewport: page.viewportSize() });
    await info.attach('workflow-outcomes', {
      body: JSON.stringify(outcomes), contentType: 'application/json',
    });
  });
}

for (const [role, account] of Object.entries(fixture.accounts)) {
  if (mobile && role !== 'admin') continue;
  test('Teaching assignment workflow for ' + role, async ({ page, request }, info) => {
    await signIn(page, account);
    const grants = new Set(fixture.permissions[role]);
    const canManage = ['accounts.view_teachers', 'accounts.manage_teaching_assignments'].every(grant => grants.has(grant));
    const employee = fixture.workflow.roles[role].markTarget;
    const base = api + 'employees/' + employee + '/';
    const payload = { session: fixture.attendance.session, academic_class: fixture.attendance.academic_class,
      section: fixture.attendance.section, subject: fixture.attendance.subject,
      effective_start: fixture.day, effective_end: fixture.day };
    const assignments = async () => {
      const response = await request.get(base + 'assignments/', { headers: control });
      expect(response.status()).toBe(200);
      return response.json();
    };
    await page.goto('/hr/employees/' + employee);
    const assign = page.getByRole('button', { name: 'Assign teacher', exact: true });
    expect(await assignments()).toHaveLength(0);
    if (canManage) {
      for (const [name, value] of Object.entries(payload)) {
        const input = page.locator('#teacher-' + name);
        if (name.startsWith('effective_')) await input.fill(value);
        else await input.selectOption(value);
      }
      const saved = page.waitForResponse(r => r.url().endsWith(base + 'assignments/') && r.request().method() === 'POST');
      await assign.click();
      expect((await saved).status()).toBe(201);
    } else {
      await expect(assign).toHaveCount(0);
      const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json();
      const denied = await page.request.post(base + 'assignments/', {
        data: payload, headers: { 'X-CSRFToken': csrf.csrf_token },
      });
      expect(denied.status()).toBe(403);
      expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
      expect(await assignments()).toHaveLength(0);
      expect((await request.post(base + 'assignments/', { data: payload, headers: control })).status()).toBe(201);
    }
    const [created] = await assignments();
    expect(created).toEqual(expect.objectContaining(payload));
    const outcomes = [{
      id: 'E-RBAC-EMPLOYEES-' + names[role] + '-04', role,
      grant: 'accounts.view_teachers + accounts.manage_teaching_assignments', endpoint: base + 'assignments/',
      resource: created.id, status: canManage ? 201 : 403, viewport: page.viewportSize(),
      persistence: 'Verified exact assignment and effective dates. Denied request preserved the empty assignment list.',
    }];
    if (mobile) {
      const next = new Date(fixture.day + 'T12:00:00Z');
      next.setUTCDate(next.getUTCDate() + 1);
      const through = next.toISOString().slice(0, 10);
      const edit = page.locator('form').filter({ has: page.getByRole('button', { name: 'Save dates', exact: true }) });
      await edit.getByLabel('Effective through').fill(through);
      const saved = page.waitForResponse(r => r.url().endsWith(base + 'assignment-dates/'));
      await edit.getByRole('button', { name: 'Save dates', exact: true }).click();
      expect((await saved).status()).toBe(200);
      expect((await assignments())[0].effective_end).toBe(through);
      await page.getByRole('button', { name: 'Assignment history', exact: true }).click();
      const history = page.getByRole('list', { name: 'Assignment history' });
      await expect(history).toContainText('hr teaching assignment created');
      await expect(history).toContainText('hr teaching assignment dates updated');
      await expect(history).toContainText(through);
      for (const [id, endpoint, persistence] of [
        ['E-MOB-01', 'assignment-dates/', 'Created assignment and persisted its revised date.'],
        ['E-MOB-02', 'assignment-history/', 'Rendered creation and dated revision history in Angular.'],
      ]) outcomes.push({ ...outcomes[0], id, endpoint: base + endpoint, status: 200, persistence });
    }
    await info.attach('workflow-outcomes', {
      body: JSON.stringify(outcomes), contentType: 'application/json',
    });
  });
}
