import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { signIn } from './auth.mjs';

const fixture = JSON.parse(readFileSync(process.env.SMS_PHASE09_FIXTURES));
const api = '/api/v1/timetables/';
const route = '/timetable';
const extended = process.env.SMS_PHASE10B === '1';
const ahead = count => {
  const date = new Date(fixture.day + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0,10);
};

const reportKinds = [
  'class', 'section', 'teacher-weekly', 'teacher-daily', 'rooms', 'workload',
  'allocations', 'unassigned', 'conflicts', 'substitutions', 'cancellations',
  'reschedules', 'revisions', 'attendance',
];

async function attachSchedulePdf(page, info, name) {
  const path = info.outputPath(name + '.pdf');
  const pdf = await page.pdf({path, format:'A4', printBackground:true});
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
  await info.attach(name, {path, contentType:'application/pdf'});
}

test('configures, reviews and publishes a scoped timetable', async ({page,browser}, info) => {
  test.setTimeout(220000);
  await signIn(page,fixture.accounts.admin);
  await page.goto(route);
  await expect(page.getByRole('heading',{name:'Timetable',exact:true})).toBeVisible();

  async function write(current, name, endpoint, confirm = false, status = 201) {
    const result = current.waitForResponse(reply => reply.url().endsWith(api + endpoint) &&
      reply.request().method() === 'POST');
    await current.getByRole('button',{name,exact:true}).click();
    if (confirm) await current.getByRole('button',{name:'Confirm',exact:true}).click();
    const response = await result;
    if (name === 'Save timetable change' && response.ok()) {
      await expect(current.getByRole('region',{name:'Timetable editor',exact:true})).toHaveCount(0);
    }
    expect(response.status(),await response.text()).toBe(status);
    return response.json();
  }
  async function fill(values, current = page) {
    for (const [key,value] of Object.entries(values)) {
      const input = current.locator('#tt-' + key);
      if (await input.evaluate(el => el.tagName === 'SELECT')) await input.selectOption(value);
      else await input.fill(value);
    }
  }

  await page.getByRole('button',{name:'Configuration',exact:true}).click();
  await page.getByRole('button',{name:'Add Shifts',exact:true}).click();
  await fill({name:'Morning fixture',code:'AM',starts_at:'08:00',ends_at:'13:00',weekdays:'0,1,2,3,4,5,6'});
  const shift = await write(page,'Save timetable change','shifts/');
  await page.getByRole('button',{name:'Add Periods and breaks',exact:true}).click();
  await fill({name:'First lesson',code:'P1',shift:shift.id,starts_at:'09:00',ends_at:'10:00'});
  const period = await write(page,'Save timetable change','periods/');
  await page.getByRole('button',{name:'Add Periods and breaks',exact:true}).click();
  await fill({name:'Morning interval',code:'BRK',shift:shift.id,starts_at:'10:00',ends_at:'10:30'});
  await page.getByLabel('Teaching period',{exact:true}).uncheck();
  const pause = await write(page,'Save timetable change','periods/');
  expect(pause.teaching).toBe(false);
  await expect(page.getByText(/Morning interval \(break\).*BRK/)).toBeVisible();

  await page.getByRole('button',{name:'Add Periods and breaks',exact:true}).click();
  await fill({name:'Overlapping interval',code:'OVR',shift:shift.id,starts_at:'09:55',ends_at:'10:05'});
  await page.getByLabel('Teaching period',{exact:true}).uncheck();
  await write(page,'Save timetable change','periods/',false,409);
  await expect(page.getByRole('alert')).toContainText(/overlap/i);
  await page.getByRole('button',{name:'Cancel',exact:true}).click();

  await page.getByRole('button',{name:'Add Periods and breaks',exact:true}).click();
  await fill({name:'Adjacent lesson',code:'P2',shift:shift.id,starts_at:'10:30',ends_at:'11:30'});
  const adjacent = await write(page,'Save timetable change','periods/');

  await page.getByRole('button',{name:'Add Shifts',exact:true}).click();
  await fill({name:'Independent shift',code:'SECOND',starts_at:'08:00',ends_at:'13:00',weekdays:'0,1,2,3,4,5,6'});
  const independent = await write(page,'Save timetable change','shifts/');
  await page.getByRole('button',{name:'Add Periods and breaks',exact:true}).click();
  await fill({name:'Independent interval',code:'BRK2',shift:independent.id,starts_at:'10:00',ends_at:'10:30'});
  await page.getByLabel('Teaching period',{exact:true}).uncheck();
  await write(page,'Save timetable change','periods/');

  await page.getByRole('button',{name:'Add Rooms',exact:true}).click();
  await fill({name:'Science lab',code:'LAB-A',kind:'laboratory',capacity:'30'});
  const room = await write(page,'Save timetable change','rooms/');
  let teachingGroup;
  if (extended) {
    await page.getByRole('button',{name:'Add Optional teaching groups',exact:true}).click();
    await fill({name:'Science option',code:'OPT-A',session:fixture.attendance.session,section:fixture.attendance.section,
      subject:fixture.attendance.subject,capacity:'10'});
    const member = page.getByRole('option',{name:/Attendance Student/});
    await expect(member).toBeAttached();
    await page.getByLabel('Group members').selectOption({label:(await member.textContent()).trim()});
    teachingGroup = await write(page,'Save timetable change','teaching-groups/');
    await page.getByRole('button',{name:'Add Teacher availability and preferences',exact:true}).click();
    await fill({teacher:fixture.timetableTeacher,weekday:String(fixture.timetableWeekday),starts_at:'09:00',ends_at:'10:00',
      effective_start:fixture.day,effective_end:ahead(12),preference:'avoid',priority:'4'});
    await write(page,'Save timetable change','teacher-availability/');
    await page.getByRole('button',{name:'Add Teacher workload policies',exact:true}).click();
    await fill({teacher:fixture.timetableTeacher,effective_start:fixture.day,effective_end:ahead(12),weekly_max:'2'});
    await write(page,'Save timetable change','workload-policies/');
  }

  await page.getByRole('button',{name:'Add Weekly subject requirements',exact:true}).click();
  await fill({session:fixture.attendance.session,section:fixture.attendance.section,
    subject:fixture.attendance.subject,minimum:'2',maximum:'2'});
  await write(page,'Save timetable change','subject-requirements/');

  const space = page.getByRole('button',{name:'Plans and revisions',exact:true});
  await space.click();
  await page.getByRole('button',{name:'Create draft timetable',exact:true}).click();
  const group = fixture.attendance;
  await fill({session:group.session,section:group.section,shift:shift.id,effective_start:fixture.day,effective_end:ahead(12)});
  const plan = await write(page,'Save timetable change','plans/');
  await page.getByRole('button',{name:'Add lesson',exact:true}).click();
  await fill({weekday:String(fixture.timetableWeekday),period:period.id,subject:group.subject,teacher:fixture.timetableTeacher,room:room.id,...(teachingGroup ? {group:teachingGroup.id} : {})});
  if (extended) {
    const subjects = page.locator('#tt-subject');
    const teachers = page.locator('#tt-teacher');
    await expect(subjects.getByRole('option',{name:'Acceptance Subject',exact:true})).toBeAttached();
    await expect(subjects.getByRole('option',{name:'Other class curriculum',exact:true})).toHaveCount(0);
    await expect(subjects.getByRole('option',{name:'Inactive curriculum',exact:true})).toHaveCount(0);
    await expect(subjects.getByRole('option',{name:'Other term curriculum',exact:true})).toHaveCount(0);
    await expect(teachers.locator(`option[value="${fixture.timetableUnassignedTeacher}"]`)).toHaveCount(0);
    if (teachingGroup) {
      const groupSelector = page.locator('#tt-group');
      await groupSelector.selectOption('');
      await expect(page.getByRole('button',{name:'Save timetable change',exact:true})).toBeDisabled();
      await groupSelector.selectOption(teachingGroup.id);
    }
    await page.getByRole('button',{name:'Create draft timetable',exact:true}).click();
    await fill({session:fixture.timetableCurriculum.session,section:fixture.timetableCurriculum.section,
      shift:shift.id,effective_start:fixture.day,effective_end:ahead(12)});
    await write(page,'Save timetable change','plans/');
    await page.getByRole('button',{name:'Add lesson',exact:true}).click();
    await expect(subjects.getByRole('option',{name:'Other class curriculum',exact:true})).toBeAttached();
    await expect(subjects.getByRole('option',{name:'Acceptance Subject',exact:true})).toHaveCount(0);
    await expect(subjects).toHaveValue('');
    await page.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
    await page.getByRole('button',{name:'Add lesson',exact:true}).click();
    await expect(subjects.getByRole('option',{name:'Acceptance Subject',exact:true})).toBeAttached();
    await expect(subjects.getByRole('option',{name:'Other class curriculum',exact:true})).toHaveCount(0);
    await fill({weekday:String(fixture.timetableWeekday),period:period.id,subject:group.subject,
      teacher:fixture.timetableTeacher,room:room.id,group:teachingGroup.id});
    await subjects.selectOption(fixture.timetableCurriculum.alternative);
    await expect(page.getByText('No eligible teachers cover the selected subject and lesson dates.')).toBeVisible();
    await expect(page.locator('#tt-teacher')).toHaveValue('');
    await expect(page.locator('#tt-group')).toHaveValue('');
    await expect(page.getByRole('button',{name:'Save timetable change',exact:true})).toBeDisabled();
    await fill({subject:group.subject,teacher:fixture.timetableTeacher,group:teachingGroup.id});
  }
  const choices = page.locator('#tt-period');
  await expect(choices.getByRole('option',{name:'Morning interval (break)'})).toBeAttached();
  await choices.selectOption(pause.id);
  await write(page,'Check conflicts','validate/',false,400);
  await expect(page.getByRole('alert')).toContainText('Choose a teaching period');
  const planVersions = await (await page.request.get(api + 'plans/' + plan.id + '/versions/')).json();
  const draftId = planVersions[0].id;
  const invalidLesson = {
    version:draftId, weekday:fixture.timetableWeekday, period:pause.id,
    subject:group.subject, teacher:fixture.timetableTeacher, room:room.id,
    ...(teachingGroup ? {group:teachingGroup.id} : {}),
  };
  const fixtureCsrf = (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token;
  const rejected = await page.request.post(api + 'entries/',{
    headers:{'X-CSRFToken':fixtureCsrf}, data:invalidLesson,
  });
  expect(rejected.status()).toBe(400);
  expect(await rejected.text()).toContain('Choose a teaching period');
  expect((await (await page.request.get(api + 'entries/?version=' + draftId)).json()).count).toBe(0);
  if (extended) {
    const rejectedSubject = await page.request.post(api + 'entries/',{
      headers:{'X-CSRFToken':fixtureCsrf},
      data:{...invalidLesson,period:period.id,subject:fixture.timetableCurriculum.foreign,group:null},
    });
    expect(rejectedSubject.status()).toBe(400);
    expect(await rejectedSubject.text()).toContain('class curriculum');
    expect((await (await page.request.get(api + 'entries/?version=' + draftId)).json()).count).toBe(0);
    if (teachingGroup) {
      const rejectedOptional = await page.request.post(api + 'entries/',{
        headers:{'X-CSRFToken':fixtureCsrf},
        data:{...invalidLesson,period:period.id,subject:group.subject,group:null},
      });
      expect(rejectedOptional.status()).toBe(400);
      const error = await rejectedOptional.json();
      expect(error).toMatchObject({
        code:400,
        message:'The request could not be completed.',
      });
      expect(JSON.stringify(error.details)).toContain(
        'Choose an explicit teaching group for an optional subject.',
      );
      expect((await (await page.request.get(api + 'entries/?version=' + draftId)).json()).count).toBe(0);
    }
    await info.attach('phase10g-eligibility',{
      body:JSON.stringify({
        plan:plan.id,wrongCurriculum:400,optionalWithoutGroup:teachingGroup ? 400 : null,
        unassignedTeacherOptions:0,rejectedWriteCount:0,
      }),
      contentType:'application/json',
    });
  }
  await choices.selectOption(period.id);
  await write(page,'Check conflicts','validate/',false,200);
  if (extended) await expect(page.getByText('Non-preferred teaching time',{exact:true})).toBeVisible();
  const entry = await write(page,'Save timetable change','entries/');
  await expect(page.getByText('Acceptance Subject',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Add lesson',exact:true}).click();
  const nextWeekday = (fixture.timetableWeekday + 1) % 7;
  await fill({weekday:String(nextWeekday),period:adjacent.id,subject:group.subject,
    teacher:fixture.timetableTeacher,room:room.id,...(teachingGroup ? {group:teachingGroup.id} : {})});
  await write(page,'Save timetable change','entries/');
  await expect(page.locator('.tt-lesson')).toHaveCount(2);
  await expect(page.getByText(/Acceptance Subject · 2 scheduled · 2–2 required/)).toBeVisible();
  const persisted = await (await page.request.get(api + 'entries/?version=' + draftId)).json();
  expect(persisted.count).toBe(2);
  await write(page,'Submit for review','plans/' + plan.id + '/submit/',true,200);

  const csrf = (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token;
  const own = {headers:{'X-CSRFToken':csrf},data:{version:entry.version}};
  expect((await page.request.post(api + 'plans/' + plan.id + '/approve/',own)).status()).toBe(403);
  const reviewer = await browser.newContext({baseURL:process.env.SMS_PHASE09_BASE_URL,viewport:page.viewportSize()});
  try {
    const approved = await reviewer.newPage();
    await signIn(approved,fixture.timetableReviewer);
    await approved.goto(route);
    await approved.getByRole('button',{name:'Plans and revisions',exact:true}).click();
    await approved.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
    const decision = approved.getByRole('button',{name:'Approve version',exact:true});
    await expect(decision).toBeVisible();
    const permissionPath = '/api/v1/roles/' + fixture.timetableReviewerRole + '/permissions/';
    const grants = fixture.timetableReviewerGrants;
    const set = permissions => page.request.put(permissionPath,{headers:own.headers,data:{permissions}});
    expect((await set(grants.filter(grant => grant !== 'accounts.approve_timetable'))).status()).toBe(200);
    try {
      const reviewerCsrf = (await (await approved.request.get('/api/v1/auth/csrf/')).json()).csrf_token;
      const denied = await approved.request.post(api + 'plans/' + plan.id + '/approve/',{
        headers:{'X-CSRFToken':reviewerCsrf},data:own.data,
      });
      expect(denied.status()).toBe(403);
      expect((await denied.json()).details.detail).toMatch(/do not have permission/i);
      const saved = await (await page.request.get(api + 'plans/' + plan.id + '/versions/')).json();
      expect(saved[0].status).toBe('review');
      await approved.reload();
      await approved.getByRole('button',{name:'Plans and revisions',exact:true}).click();
      await approved.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
      await expect(decision).toHaveCount(0);
    } finally {
      expect((await set(grants)).status()).toBe(200);
    }
    await approved.reload();
    await approved.getByRole('button',{name:'Plans and revisions',exact:true}).click();
    await approved.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
    await write(approved,'Approve version','plans/' + plan.id + '/approve/',true,200);
  } finally {
    await reviewer.close();
  }
  await page.reload();
  await space.click();
  await page.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
  await write(page,'Publish version','plans/' + plan.id + '/publish/',true,200);
  await expect(page.getByRole('button',{name:'Edit lesson',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Remove lesson',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Copy to new draft',exact:true})).toBeVisible();
  const immutable = await page.request.patch(api + 'entries/' + entry.id + '/',{
    headers:{'X-CSRFToken':csrf}, data:{notes:'Unauthorized change to published fixture'},
  });
  expect(immutable.status()).toBe(409);
  const retained = await (await page.request.get(api + 'entries/' + entry.id + '/')).json();
  expect(retained.notes).toBe(entry.notes);
  const savedBreak = await (await page.request.get(api + 'periods/' + pause.id + '/')).json();
  expect(savedBreak).toMatchObject({id:pause.id,teaching:false,starts_at:'10:00:00',ends_at:'10:30:00'});

  await page.getByRole('button',{name:'Published schedule',exact:true}).click();
  await page.getByLabel('Starting date').fill(fixture.day);
  await page.getByRole('button',{name:'Show schedule',exact:true}).click();
  const lesson = page.locator('.tt-lesson').filter({hasText:'09:00–10:00'});
  await expect(lesson).toContainText('Science lab');
  await expect(lesson).toContainText('09:00–10:00');
  await expect(lesson).toContainText('fixture-teacher');
  await expect(page.locator('.tt-lesson').filter({hasText:'10:30–11:30'})).toContainText('Acceptance Class');
  await page.emulateMedia({media:'print'});
  await expect(page.getByText(/Browser Academy · Published schedule from/)).toBeVisible();
  await expect(lesson.getByText('Acceptance term · Published revision 1')).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Timetable workspace'})).toBeHidden();
  await expect(lesson.getByRole('link',{name:'Open attendance'})).toBeHidden();
  await expect(page.getByText('Timetable publish recorded.')).toBeHidden();
  await attachSchedulePdf(page, info, 'class-schedule');
  await page.emulateMedia({media:'screen'});
  const download = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download CSV',exact:true}).click();
  expect((await download).suggestedFilename()).toBe('timetable.csv');
  const teacher = await browser.newContext({baseURL:process.env.SMS_PHASE09_BASE_URL,viewport:page.viewportSize()});
  try {
    const scoped = await teacher.newPage();
    await signIn(scoped,fixture.accounts.teacher);
    await scoped.goto(route);
    await scoped.getByLabel('Starting date').fill(fixture.day);
    await scoped.getByRole('button',{name:'Show schedule',exact:true}).click();
    const ownLesson = scoped.locator('.tt-lesson').filter({hasText:'09:00–10:00'});
    await expect(ownLesson).toContainText('Acceptance Subject');
    await expect(scoped.locator('.tt-lesson').filter({hasText:'10:30–11:30'})).toContainText('Acceptance Subject');
    await scoped.emulateMedia({media:'print'});
    await expect(ownLesson.getByText('Acceptance term · Published revision 1')).toBeVisible();
    await expect(scoped.getByRole('button',{name:'Print schedule'})).toBeHidden();
    await expect(ownLesson.getByRole('link',{name:'Open attendance'})).toBeHidden();
    await attachSchedulePdf(scoped, info, 'teacher-schedule');
    await scoped.emulateMedia({media:'screen'});
    await expect(scoped.getByRole('button',{name:'Plans and revisions',exact:true})).toHaveCount(0);
    expect((await scoped.request.get(api + 'plans/')).status()).toBe(403);
    await ownLesson.getByRole('link',{name:'Open attendance',exact:true}).click();
    await expect(scoped.getByRole('heading',{name:'Student attendance',exact:true})).toBeVisible();
    await scoped.getByRole('button',{name:'Load roster',exact:true}).click();
    await expect(scoped.getByRole('heading',{name:'Roster preview',exact:true})).toBeVisible();
    const created = scoped.waitForResponse(reply => reply.url().endsWith('/api/v1/attendance/') &&
      reply.request().method() === 'POST');
    await scoped.getByRole('button',{name:'Start draft',exact:true}).click();
    const register = await created;
    expect(register.status()).toBe(201);
    expect((await register.json()).schedule_snapshot).toMatchObject({
      entry:entry.id,version:entry.version,period:'P1',teacher:fixture.timetableTeacher,
      ...(teachingGroup ? {group:teachingGroup.id} : {}),
    });
    await expect(scoped.getByText('Published timetable · 09:00–10:00',{exact:true})).toBeVisible();
  } finally {
    await teacher.close();
  }
  if (process.env.SMS_PHASE10E_CORE === '1') {
    const width = info.project.name === 'timetable-mobile' ? 390 : 1440;
    expect(await page.evaluate(() => innerWidth)).toBe(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await info.attach('phase10e-closure',{
      body:JSON.stringify({
        break:{id:pause.id,invalidStatus:rejected.status(),persisted:savedBreak.teaching === false,adjacent:adjacent.id},
        classPlan:{id:plan.id,version:draftId,entries:persisted.count,published:true},
        publication:{entry:entry.id,mutationStatus:immutable.status(),notesUnchanged:retained.notes === entry.notes},
      }),
      contentType:'application/json',
    });
    return;
  }

  let leaveChange;
  if (extended) {
    await expect(lesson.getByText('approved leave',{exact:true})).toHaveCount(0);
    await page.locator('select[name="schedule-teacher"]').selectOption(fixture.timetableTeacher);
    await page.getByLabel('Starting date').fill(ahead(1));
    await page.getByRole('button',{name:'Show schedule',exact:true}).click();
    const affected = page.locator('.tt-lesson').filter({hasText:'10:30–11:30'});
    await expect(affected.getByText('approved leave',{exact:true})).toBeVisible();
    await page.locator('select[name="schedule-teacher"]').selectOption('');
    await page.getByRole('button',{name:'Daily changes',exact:true}).click();
    await page.getByRole('button',{name:'Find published lessons',exact:true}).click();
    await page.getByRole('button',{name:'Record daily change',exact:true}).click();
    const scheduled = page.locator('#tt-entry');
    const eligible = await scheduled.locator('option').filter({hasText:'P2'}).getAttribute('value');
    await fill({entry:eligible,kind:'substitute',teacher:fixture.timetableCoverTeacher,reason:'Approved leave cover'});
    leaveChange = await write(page,'Save timetable change','exceptions/');
    await page.getByRole('button',{name:'Published schedule',exact:true}).click();
    await expect(affected).toContainText('fixture-cover-teacher');
    const preserved = await (await page.request.get(api + 'entries/' + eligible + '/')).json();
    expect(preserved.teacher).toBe(fixture.timetableTeacher);
    await page.getByLabel('Starting date').fill(fixture.day);
    await page.getByRole('button',{name:'Show schedule',exact:true}).click();
    await expect(lesson).toContainText('fixture-teacher');
  }
  await page.getByRole('button',{name:'Daily changes',exact:true}).click();
  await page.getByRole('button',{name:'Record daily change',exact:true}).click();
  await fill({entry:entry.id,reason:'Fixture cancellation'});
  await write(page,'Save timetable change','exceptions/');
  await page.getByRole('button',{name:'Published schedule',exact:true}).click();
  await expect(lesson).toContainText('cancelled');
  if (extended) {
    await page.getByRole('button',{name:'Daily changes',exact:true}).click();
    await page.getByLabel('Lesson date').fill(ahead(7));
    await page.getByRole('button',{name:'Find published lessons',exact:true}).click();
    await page.getByRole('button',{name:'Record daily change',exact:true}).click();
    await fill({entry:entry.id,kind:'rescheduled',destination_date:ahead(8),period:period.id,reason:'Move fixture lesson'});
    await write(page,'Save timetable change','exceptions/');
    await page.getByRole('button',{name:'Reports',exact:true}).click();
    await page.getByRole('combobox',{name:'Report',exact:true}).selectOption('reschedules',{timeout:10000});
    await page.getByLabel('From date').fill(ahead(7));
    await page.getByLabel('Through date').fill(ahead(8));
    await page.getByRole('button',{name:'Run report',exact:true}).click();
    await expect(page.getByText('1 records',{exact:true})).toBeVisible();
    await expect(page.getByText(ahead(8),{exact:false}).first()).toBeVisible();
    const csv = page.waitForEvent('download');
    await page.getByRole('link',{name:'Export report CSV'}).click();
    expect((await csv).suggestedFilename()).toBe('reschedules.csv');
    await page.getByLabel('Report class').selectOption(group.academic_class);
    await page.getByLabel('Report session').selectOption(group.session);
    const reportOutcomes = [];
    for (const kind of reportKinds) {
      await page.getByRole('combobox',{name:'Report',exact:true}).selectOption(kind);
      const received = page.waitForResponse(reply =>
        new URL(reply.url()).pathname === api + 'reports/' + kind + '/' &&
        !new URL(reply.url()).searchParams.has('format_type'));
      await page.getByRole('button',{name:'Run report',exact:true}).click();
      const response = await received;
      expect(response.status()).toBe(200);
      const data = await response.json();
      const filters = new URL(response.url()).searchParams;
      expect(filters.get('date')).toBe(ahead(7));
      expect(filters.get('through')).toBe(ahead(8));
      expect(filters.get('academic_class')).toBe(group.academic_class);
      expect(filters.get('session')).toBe(group.session);
      await expect(page.getByText(data.count + ' records',{exact:true})).toBeVisible();
      const exportStarted = page.waitForEvent('download');
      await page.getByRole('link',{name:'Export report CSV'}).click();
      const exported = await exportStarted;
      expect(exported.suggestedFilename()).toBe(kind + '.csv');
      const csvText = readFileSync(await exported.path(),'utf8');
      expect(csvText.startsWith('\ufeff')).toBe(true);
      if (data.results.length) {
        const firstVisibleField = Object.entries(data.results[0]).find(([key, value]) =>
          key.endsWith('_name') && typeof value === 'string');
        if (firstVisibleField) {
          expect(csvText).toContain(firstVisibleField[1]);
        }
      }
      reportOutcomes.push({kind, count:data.count, from:ahead(7), through:ahead(8), export:exported.suggestedFilename()});
    }
    await info.attach('report-outcomes',{body:JSON.stringify(reportOutcomes),contentType:'application/json'});

  }

  await space.click();
  await page.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
  await page.getByRole('button',{name:'Copy to new draft',exact:true}).click();
  await fill({effective_start:ahead(14),effective_end:ahead(20)});
  const successor = await write(page,'Save timetable change','plans/' + plan.id + '/new-version/');
  const copiedLesson = page.locator('.tt-lesson').filter({hasText:'First lesson'});
  if (extended) {
    const created = page.waitForResponse(reply =>
      reply.url().endsWith(api + 'teaching-groups/' + teachingGroup.id + '/successor/') &&
      reply.request().method() === 'POST');
    await page.getByRole('button',{name:'Create successor roster',exact:true}).click({timeout:10000});
    await page.getByRole('button',{name:'Confirm',exact:true}).click();
    const receipt = await created;
    expect(receipt.status(),await receipt.text()).toBe(201);
    const roster = await receipt.json();
    expect(roster).toMatchObject({
      predecessor:teachingGroup.id,effective_version:successor.id,enrollments:teachingGroup.enrollments,
    });
    await expect(page.getByText(/Science option.*Successor roster/)).toBeVisible();
    await space.click();
  }
  await copiedLesson.getByRole('button',{name:'Edit lesson',exact:true}).click();
  await page.locator('#tt-notes').fill('Successor-only notes');
  const editedReceipt = page.waitForResponse(reply =>
    reply.url().includes(api + 'entries/') && reply.request().method() === 'PATCH');
  await page.getByRole('button',{name:'Save timetable change',exact:true}).click();
  expect((await editedReceipt).status()).toBe(200);
  await expect(page.getByRole('region',{name:'Timetable editor',exact:true})).toHaveCount(0);
  await write(page,'Submit for review','plans/' + plan.id + '/submit/',true,200);
  const successorReviewer = await browser.newContext({
    baseURL:process.env.SMS_PHASE09_BASE_URL,viewport:page.viewportSize(),
  });
  try {
    const authorized = await successorReviewer.newPage();
    await signIn(authorized,fixture.timetableReviewer);
    await authorized.goto(route);
    await authorized.getByRole('button',{name:'Plans and revisions',exact:true}).click();
    await authorized.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
    await write(authorized,'Approve version','plans/' + plan.id + '/approve/',true,200);
  } finally {
    await successorReviewer.close();
  }
  await page.reload();
  await space.click();
  await page.getByRole('button',{name:/Acceptance Section.*Acceptance term/}).click();
  await write(page,'Publish version','plans/' + plan.id + '/publish/',true,200);
  const historical = await (await page.request.get(api + 'daily/?date=' + fixture.day)).json();
  const future = await (await page.request.get(api + 'daily/?date=' + ahead(14))).json();
  expect(historical.lessons.find(row => row.entry === entry.id)?.version).toBe(draftId);
  expect(future.lessons.find(row => row.period === 'P1')?.version).toBe(successor.id);
  const original = await (await page.request.get(api + 'entries/' + entry.id + '/')).json();
  expect(original.notes).toBe(entry.notes);

  if (extended) {
    await page.getByRole('button',{name:'Daily changes',exact:true}).click();
    await page.getByLabel('Lesson date').fill(ahead(8));
    await page.getByRole('button',{name:'Find published lessons',exact:true}).click();
    await page.getByRole('button',{name:'Record daily change',exact:true}).click();
    const originalSecond = persisted.results.find(row => row.period === adjacent.id);
    await page.locator('#tt-entry').selectOption(originalSecond.id);
    await fill({kind:'rescheduled',destination_date:ahead(16),period:adjacent.id,
      reason:'Cross-revision fixture move'});
    const move = await write(page,'Save timetable change','exceptions/');
    expect(move.destination_version).toBe(successor.id);
    const response = await (await page.request.get(api + 'daily/?date=' + ahead(16))).json();
    expect(response.lessons).toHaveLength(1);
    expect(response.lessons[0]).toMatchObject({
      entry:originalSecond.id,version:successor.id,source_version:draftId,
      destination_version:successor.id,group:move.destination_group,
    });
    await info.attach('phase10f-history',{
      body:JSON.stringify({source:draftId,destination:successor.id,roster:move.destination_group}),
      contentType:'application/json',
    });
  }

  await page.getByRole('button',{name:'Reports',exact:true}).click();
  await page.getByRole('combobox',{name:'Report',exact:true}).selectOption('class');
  await page.getByLabel('From date').fill(fixture.day);
  await page.getByLabel('Through date').fill(ahead(20));
  await page.getByLabel('Report class').selectOption(group.academic_class);
  await page.getByLabel('Report session').selectOption(group.session);
  await page.evaluate(() => {window.print = () => document.body.setAttribute('data-report-printed','yes');});
  await page.getByRole('button',{name:'Print report',exact:true}).click();
  await expect(page.locator('body')).toHaveAttribute('data-report-printed','yes');
  await page.emulateMedia({media:'print'});
  const printable = page.getByRole('region',{name:'Printable report',exact:true});
  await expect(printable).toContainText('Browser Academy');
  await expect(printable).toContainText('Acceptance Class');
  expect(await printable.locator('.tt-lesson').count()).toBeGreaterThan(5);
  await expect(page.getByRole('button',{name:'Print report',exact:true})).toBeHidden();
  await attachSchedulePdf(page, info, 'historical-class-report');
  await page.emulateMedia({media:'screen'});
  await page.getByRole('combobox',{name:'Report',exact:true}).selectOption('rooms');
  await page.getByRole('button',{name:'Print report',exact:true}).click();
  await expect(page.locator('body')).toHaveAttribute('data-report-printed','yes');
  await page.emulateMedia({media:'print'});
  const roomReport = page.getByRole('region',{name:'Printable report',exact:true});
  await expect(roomReport).toContainText('rooms');
  await expect(roomReport).toContainText('Science lab');
  expect(await roomReport.locator('.tt-lesson').count()).toBeGreaterThan(0);
  await attachSchedulePdf(page, info, 'room-usage-report');
  await page.emulateMedia({media:'screen'});
  await info.attach('room-report-print',{
    body:JSON.stringify({kind:'rooms',room:'Science lab',printed:true}),
    contentType:'application/json',
  });

  await info.attach('phase10e-closure',{
    body:JSON.stringify({
      break:{id:pause.id,invalidStatus:rejected.status(),persisted:savedBreak.teaching === false,adjacent:adjacent.id},
      classPlan:{id:plan.id,version:draftId,entries:persisted.count,published:true},
      leave:leaveChange ? {id:leaveChange.id,kind:leaveChange.kind,date:leaveChange.date} : null,
      publication:{entry:entry.id,mutationStatus:immutable.status(),notesUnchanged:original.notes === entry.notes,successor:successor.id},
    }),
    contentType:'application/json',
  });

  const width = info.project.name === 'timetable-mobile' ? 390 : 1440;
  expect(await page.evaluate(() => innerWidth)).toBe(width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});

test('revokes timetable report read and CSV access from a live session', async ({page,browser}, info) => {
  await signIn(page, fixture.accounts.admin);
  const csrf = (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token;
  const role = '/api/v1/roles/' + fixture.timetableReviewerRole + '/permissions/';
  const exportGrant = 'accounts.export_timetable';
  const viewGrant = 'accounts.view_timetable';
  const settingsGrant = 'accounts.change_timetable_settings';
  const grants = fixture.timetableReviewerGrants;
  const update = async permissions => {
    const response = await page.request.put(role, {
      headers:{'X-CSRFToken':csrf}, data:{permissions},
    });
    expect(response.status(), await response.text()).toBe(200);
  };
  const reviewer = await browser.newContext({
    baseURL:process.env.SMS_PHASE09_BASE_URL, viewport:page.viewportSize(),
  });
  const scoped = await reviewer.newPage();
  const reportEndpoint = api + 'reports/class/?date=' + fixture.day;
  const exportEndpoint = reportEndpoint + '&format_type=csv';
  const settingsEndpoint = api + 'settings/';
  let capacitySetting;
  try {
    await update([...grants, exportGrant]);
    await signIn(scoped, fixture.timetableReviewer);
    await scoped.goto(route);
    await scoped.getByRole('button',{name:'Reports',exact:true}).click();
    const csv = scoped.getByRole('link',{name:'Export report CSV'});
    await expect(csv).toBeVisible();
    expect((await scoped.request.get(exportEndpoint)).status()).toBe(200);

    await update(grants);
    const exportDenial = await scoped.request.get(exportEndpoint);
    expect(exportDenial.status()).toBe(403);
    expect(await exportDenial.text()).toMatch(/do not have permission/i);
    expect((await scoped.request.get(reportEndpoint)).status()).toBe(200);
    await scoped.reload();
    await scoped.getByRole('button',{name:'Reports',exact:true}).click();
    await expect(csv).toHaveCount(0);

    const currentSettings = await (await page.request.get(settingsEndpoint)).json();
    capacitySetting = currentSettings.enforce_capacity;
    const settingsCsrf = (await (await scoped.request.get('/api/v1/auth/csrf/')).json()).csrf_token;
    await update([...grants, settingsGrant]);
    const capacityAllowed = await scoped.request.patch(settingsEndpoint,{
      headers:{'X-CSRFToken':settingsCsrf},
      data:{enforce_capacity:!capacitySetting},
    });
    expect(capacityAllowed.status(),await capacityAllowed.text()).toBe(200);
    expect((await capacityAllowed.json()).enforce_capacity).toBe(!capacitySetting);

    await update(grants);
    const capacityDenied = await scoped.request.patch(settingsEndpoint,{
      headers:{'X-CSRFToken':settingsCsrf},
      data:{enforce_capacity:capacitySetting},
    });
    expect(capacityDenied.status()).toBe(403);
    const retainedSettings = await (await page.request.get(settingsEndpoint)).json();
    expect(retainedSettings.enforce_capacity).toBe(!capacitySetting);

    await update(grants.filter(grant => grant !== viewGrant));
    const reportDenial = await scoped.request.get(reportEndpoint);
    expect(reportDenial.status()).toBe(403);
    const denied = await reportDenial.json();
    expect(denied.details.detail).toMatch(/do not have permission/i);
    expect(denied).not.toHaveProperty('results');
    await scoped.reload();
    await expect(scoped.getByRole('button',{name:'Reports',exact:true})).toHaveCount(0);
    await expect(scoped.getByRole('heading',{name:'Timetable',exact:true})).toHaveCount(0);

    await info.attach('report-revocation',{
      body:JSON.stringify({
        read:reportDenial.status(),
        export:exportDenial.status(),
        capacity:{granted:capacityAllowed.status(),revoked:capacityDenied.status()},
      }),
      contentType:'application/json',
    });
  } finally {
    await update(grants);
    if (capacitySetting !== undefined) {
      const restored = await page.request.patch(settingsEndpoint,{
        headers:{'X-CSRFToken':csrf},data:{enforce_capacity:capacitySetting},
      });
      expect(restored.status(),await restored.text()).toBe(200);
    }
    await reviewer.close();
  }
});

test('checks timetable operations across the five fixture roles', async ({browser}, info) => {
  test.setTimeout(120000);
  const roles = ['admin','teacher','hr','payroll','restricted'];
  const operations = [
    {name:'timetable settings read',method:'get',endpoint:api + 'settings/',grant:'accounts.view_timetable',allowed:200},
    {name:'draft read',method:'get',endpoint:api + 'plans/',grant:'accounts.view_timetable',allowed:200},
    {name:'room report read',method:'get',endpoint:api + 'reports/rooms/?date=' + fixture.day,
      any:['accounts.view_timetable','accounts.view_own_timetable'],allowed:200},
    {name:'room report export',method:'get',endpoint:api + 'reports/rooms/?date=' + fixture.day + '&format_type=csv',
      grant:'accounts.export_timetable',any:['accounts.view_timetable','accounts.view_own_timetable'],allowed:200},
    {name:'capacity override',method:'patch',endpoint:api + 'settings/',grant:'accounts.change_timetable_settings',
      data:{enforce_capacity:true},allowed:200},
    {name:'configuration write',method:'post',endpoint:api + 'shifts/',
      grant:'accounts.change_timetable_settings',
      data:{name:'RBAC matrix shift',code:'RBAC-MATRIX',starts_at:'08:00',ends_at:'12:00',weekdays:[0]},allowed:201},
    {name:'plan creation',method:'post',endpoint:api + 'plans/',grant:'accounts.manage_timetable',data:{},allowed:400},
    {name:'lesson write',method:'post',endpoint:api + 'entries/',grant:'accounts.manage_timetable',data:{},allowed:400},
    {name:'daily exception write',method:'post',endpoint:api + 'exceptions/',
      grant:'accounts.change_timetable_exceptions',data:{},allowed:400},
  ];
  const outcomes = [];
  for (const role of roles) {
    const context = await browser.newContext({baseURL:process.env.SMS_PHASE09_BASE_URL});
    try {
      const page = await context.newPage();
      await signIn(page,fixture.accounts[role]);
      const grants = fixture.permissions[role] || [];
      await page.goto(route);
      const workspace = page.getByRole('navigation',{name:'Timetable workspace'});
      const hasView = grants.includes('accounts.view_timetable');
      const hasOwnView = grants.includes('accounts.view_own_timetable');
      if (hasView) {
        await expect(workspace).toBeVisible();
        await expect(workspace.getByRole('button',{name:'Reports',exact:true})).toBeVisible();
        await workspace.getByRole('button',{name:'Configuration',exact:true}).click();
        const editSettings = page.getByRole('button',{name:'Edit settings',exact:true});
        if (grants.includes('accounts.change_timetable_settings')) await expect(editSettings).toBeVisible();
        else await expect(editSettings).toHaveCount(0);
        await workspace.getByRole('button',{name:'Plans and revisions',exact:true}).click();
        const createDraft = page.getByRole('button',{name:'Create draft timetable',exact:true});
        if (grants.includes('accounts.manage_timetable')) await expect(createDraft).toBeVisible();
        else await expect(createDraft).toHaveCount(0);
      } else {
        await expect(workspace).toHaveCount(0);
        const printSchedule = page.getByRole('button',{name:'Print schedule',exact:true});
        if (hasOwnView) await expect(printSchedule).toBeVisible();
        else await expect(printSchedule).toHaveCount(0);
      }
      const csrf = (await (await page.request.get('/api/v1/auth/csrf/')).json()).csrf_token;
      for (const operation of operations) {
        const allowed = (!operation.any || operation.any.some(grant => grants.includes(grant))) &&
          (!operation.grant || grants.includes(operation.grant)) &&
          (!operation.also || grants.includes(operation.also));
        const options = operation.method === 'get' ? undefined : {
          headers:{'X-CSRFToken':csrf},data:operation.data,
        };
        const response = await page.request[operation.method](operation.endpoint,options);
        expect(response.status(),role + ': ' + operation.name + ': ' + await response.text())
          .toBe(allowed ? operation.allowed : 403);
        outcomes.push({role,operation:operation.name,status:response.status()});
      }
    } finally {
      await context.close();
    }
  }
  await info.attach('five-role-timetable-matrix',{
    body:JSON.stringify(outcomes),contentType:'application/json',
  });
});
