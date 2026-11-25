import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const route = '/hr/salary-structures';
const api = '/api/v1' + route + '/';
const name = 'Dated salary approval fixture';
const draft = {
  name, code: 'APPROVAL-FIXTURE', basis: 'monthly', basic: '1200.45',
  effective_from: '2099-01-01', effective_through: '2099-12-31',
  components: [
    {label: 'Fixture allowance', kind: 'earning', amount: '17.25'},
    {label: 'Fixture deduction', kind: 'deduction', amount: '2.30'},
  ],
};

async function token(page) {
  return {'X-CSRFToken': (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token};
}

async function record(page, button, endpoint, method = 'POST', confirmation = false) {
  const response = page.waitForResponse(reply => reply.url().endsWith(endpoint) && reply.request().method() === method);
  await button.click();
  if (confirmation) await page.getByRole('button', {name: 'Confirm', exact: true}).click();
  return response;
}

test('salary structure decisions protect the approved revision', async ({page, browser, request}, info) => {
  test.setTimeout(90000);
  await signIn(page, fixture.accounts.admin);
  const admin = await token(page);
  const control = {Cookie:fixture.control.cookie, 'X-CSRFToken':fixture.control.csrf};
  const historicalPaths = fixture.finance
    ? ['payroll/' + fixture.finance.run + '/', 'payslips/' + fixture.finance.entry + '/',
      'salary-payments/' + fixture.finance.payment + '/'] : [];
  const historical = () => Promise.all(historicalPaths.map(async path => {
    const reply = await request.get('/api/v1/hr/' + path, {headers:control});
    expect(reply.status()).toBe(200);
    return reply.body();
  }));
  const historyBefore = await historical();
  await page.goto(route);
  for (const key of ['name', 'code', 'basic', 'effective_from', 'effective_through']) {
    await page.locator('#' + key).fill(draft[key]);
  }
  for (const [index, component] of draft.components.entries()) {
    await page.getByRole('button', {name:'Add component'}).click();
    await page.locator('[formcontrolname=label]').nth(index).fill(component.label);
    await page.locator('[formcontrolname=kind]').nth(index).selectOption(component.kind);
    await page.locator('[formcontrolname=amount]').nth(index).fill(component.amount);
  }
  const saved = await record(page, page.getByRole('button', {name:'Save draft', exact:true}), api);
  expect(saved.status()).toBe(201);
  const structure = await saved.json();
  const path = api + structure.id + '/';
  const revision = () => request.get(path, {headers:control}).then(r => r.json());
  const history = () => request.get(path + 'approvals/', {headers:control}).then(r => r.json());
  const row = page.getByRole('row').filter({hasText:name});
  expect(await revision()).toMatchObject({active:false, status:'draft', revision:1});
  expect((await page.request.patch(path, {headers:admin, data:{active:true}})).status()).toBe(400);
  const submit = async () => {
    const response = await record(page, row.getByRole('button', {name:'Submit for approval', exact:true}),
      path + 'submit/', 'POST', true);
    expect(response.status()).toBe(201);
    return response.json();
  };
  const first = await submit();
  expect(first.snapshot).toMatchObject({effective_from:draft.effective_from, components:draft.components});
  const denied = await page.request.post(path + 'approve/', {headers:admin, data:{approval:first.id}});
  expect(denied.status()).toBe(403);
  expect(JSON.stringify(await denied.json())).toMatch(/different user/i);
  expect((await history())[0]).toMatchObject({id:first.id, decision:'pending'});

  const reviewerContext = await browser.newContext({baseURL:process.env.SMS_PHASE09_BASE_URL, viewport:page.viewportSize()});
  try {
    const reviewed = await reviewerContext.newPage();
    await signIn(reviewed, fixture.accounts.payroll);
    const reviewer = await token(reviewed);
    const roleEndpoint = '/api/v1/roles/' + fixture.approvalReviewerRole + '/permissions/';
    const grants = fixture.permissions.payroll;
    const set = permissions => request.put(roleEndpoint, {headers:control, data:{permissions}});
    const open = async () => {
      await reviewed.goto(route);
      await reviewed.getByRole('button', {name:'View pending approvals', exact:true}).click();
      await reviewed.getByRole('listitem').filter({hasText:name})
        .getByRole('button', {name:'Review revision', exact:true}).click();
      await expect(reviewed.getByRole('heading', {name:'Approval history · ' + name, exact:true})).toBeVisible();
    };
    await open();
    const approve = reviewed.getByRole('button', {name:'Approve revision', exact:true});
    await expect(approve).toBeVisible();
    expect((await set(grants.filter(permission => permission !== 'accounts.approve_salary_structure'))).status()).toBe(200);
    try {
      const result = await reviewed.request.post(path + 'approve/', {headers:reviewer, data:{approval:first.id}});
      expect(result.status()).toBe(403);
      expect((await result.json()).details.detail).toMatch(/do not have permission/i);
      expect((await history())[0]).toMatchObject({id:first.id, decision:'pending'});
      await open();
      await expect(approve).toHaveCount(0);
    } finally {
      expect((await set(grants)).status()).toBe(200);
    }
    await open();
    const reject = reviewed.getByRole('button', {name:'Reject revision', exact:true});
    await expect(reject).toBeDisabled();
    await reviewed.getByLabel('Rejection reason').fill('Revise the fixture allowance');
    expect((await record(reviewed, reject, path + 'reject/', 'POST', true)).status()).toBe(200);
    expect((await page.request.post(path + 'activate/', {headers:admin, data:{approval:first.id}})).status()).toBe(409);
    expect((await history())[0]).toMatchObject({decision:'rejected', reason:'Revise the fixture allowance'});

    await page.reload();
    await row.getByRole('button', {name:'Edit', exact:true}).click();
    await page.locator('[formcontrolname=amount]').first().fill('18.35');
    expect((await record(page, page.getByRole('button', {name:'Save draft', exact:true}),
      path, 'PATCH')).status()).toBe(200);
    const second = await submit();
    expect(second.revision).toBe(2);
    expect(second.snapshot.components).toEqual([{...draft.components[0], amount:'18.35'}, draft.components[1]]);
    await open();
    const decision = reviewed.waitForResponse(reply => reply.url().endsWith(path + 'approve/'));
    await approve.click();
    const dialog = reviewed.getByRole('dialog');
    await expect(dialog).toContainText('Fixture allowance · earning · 18.35');
    await expect(dialog).toContainText(draft.effective_from);
    await reviewed.getByRole('button', {name:'Confirm', exact:true}).click();
    expect((await decision).status()).toBe(200);
    await page.reload();
    expect((await record(page, row.getByRole('button', {name:'Activate approved structure', exact:true}),
      path + 'activate/', 'POST', true)).status()).toBe(200);
    await expect(row.getByRole('button', {name:'Edit', exact:true})).toHaveCount(0);
    expect(await revision()).toMatchObject({active:true, legacy_active:false, revision:2, status:'active'});
    await row.getByRole('button', {name:'View approval history', exact:true}).click();
    const approvedHistory = page.locator('article').filter({has:page.getByRole('heading', {name:'Revision 2 · approved',exact:true})});
    await expect(approvedHistory.getByText(/Reviewed by fixture-payroll/)).toBeVisible();
    await expect(page.getByText(/Activated by fixture-admin/)).toBeVisible();
    const [approved, rejected] = await history();
    expect(approved).toMatchObject({id:second.id, decision:'approved', submitter:fixture.accounts.admin.username,
      reviewer:fixture.accounts.payroll.username, activator:fixture.accounts.admin.username});
    expect(approved.reviewed_at).toBeTruthy();
    expect(approved.activated_at).toBeTruthy();
    expect(rejected.snapshot).toEqual(first.snapshot);
    if (fixture.finance) {
      await page.goto('/hr/salary-assignments');
      await page.locator('#employee').selectOption(fixture.finance.employee);
      await page.locator('#structure').selectOption(structure.id);
      await page.locator('#start_date').fill('2099-01-01');
      await page.locator('#end_date').fill('2099-01-31');
      const assignment = await record(page, page.getByRole('button', {name:'Save record',exact:true}), '/api/v1/hr/salary-assignments/');
      expect(assignment.status()).toBe(201);
      expect(await assignment.json()).toMatchObject({structure:structure.id,start_date:'2099-01-01'});
      expect(await historical()).toEqual(historyBefore);
    }
    const size = info.project.name === 'approval-mobile' ? {width:390,height:844} : {width:1440,height:900};
    expect(page.viewportSize()).toEqual(size);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width);
    await info.attach('salary-approval-evidence', {contentType:'application/json',body:JSON.stringify({
      structure:structure.id, approval:second.id, revision:2,
      protected: true, revocationStatus:403, separateReviewer:true, viewport:size,
    })});
  } finally {
    await reviewerContext.close();
  }
});

for (const role of ['hr', 'teacher', 'restricted']) {
  if (process.env.SMS_PHASE09_APPROVAL !== 'desktop') continue;
  test('salary workflow denials for ' + role, async ({page, request}) => {
    const control = {Cookie:fixture.control.cookie, 'X-CSRFToken':fixture.control.csrf};
    const reviewer = {Cookie:fixture.salaryReviewer.cookie, 'X-CSRFToken':fixture.salaryReviewer.csrf};
    await signIn(page, fixture.accounts[role]);
    const headers = await token(page);
    const grants = new Set(fixture.permissions[role]);
    const data = {...draft, name:'Approval matrix ' + role, code:'MATRIX-' + role};
    const permitted = async (path, body, status, credentials = control) => {
      const response = await request.post(path, {headers:credentials,data:body});
      expect(response.status()).toBe(status);
      return response.json();
    };
    const noAccess = async (path, grant, data) => {
      expect(grants.has('accounts.' + grant)).toBe(false);
      const response = data ? await page.request.post(path,{headers,data}) : await page.request.get(path);
      expect(response.status()).toBe(403);
      const text = await response.text();
      expect(JSON.parse(text).details.detail).toMatch(/do not have permission/i);
      expect(text).not.toContain(draft.basic);
      expect(text).not.toContain(draft.components[0].label);
    };
    await page.goto(route);
    await expect(page).toHaveURL(/\/access-denied$/);
    await noAccess(api, 'manage_salary_setup', data);
    const query = () => request.get(api,{headers:control,params:{search:data.code}}).then(r => r.json());
    expect((await query()).results).toEqual([]);
    const created = await permitted(api,data,201);
    const path = api + created.id + '/';
    const approvals = () => request.get(path + 'approvals/',{headers:control}).then(r => r.json());
    const detail = await request.get(path,{headers:control});
    expect(detail.status()).toBe(200);
    await noAccess(path, 'view_salary_setup');
    await noAccess(path + 'submit/', 'submit_salary_structure', {});
    expect(await approvals()).toEqual([]);
    const submitted = await permitted(path + 'submit/',{},201);
    const body = {approval:submitted.id};
    await noAccess(path + 'approvals/', 'view_salary_structure_approvals');
    await noAccess(api + 'pending-approvals/', 'view_salary_structure_approvals');
    await noAccess(path + 'approve/', 'approve_salary_structure', body);
    await noAccess(path + 'reject/', 'approve_salary_structure', {...body,reason:'Fixture rejection'});
    expect(await approvals()).toEqual([submitted]);
    const approved = await permitted(path + 'approve/',body,200,reviewer);
    await noAccess(path + 'activate/', 'activate_salary_structure', body);
    expect(await approvals()).toEqual([approved]);
    expect((await (await request.get(path,{headers:control})).json()).active).toBe(false);
    await permitted(path + 'activate/',body,200);
  });
}
