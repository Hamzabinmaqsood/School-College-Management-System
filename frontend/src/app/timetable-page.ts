import { Component, inject, signal } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { AcademicWorkspace, Field, recordForm } from './academic-tools';
import { AdminApi, Page, RequestState } from './admin';
import { AuthService } from './auth';

type Row = Record<string, string | number | boolean | null>;
interface Lesson {
  entry: string; date: string; class_name: string; section_name: string; period: string;
  starts_at: string; ends_at: string; subject_name: string; teacher_name: string;
  revision: number; session_name: string;
  session: string; academic_class: string; section: string; subject: string;
  group_name: string | null; destination_date?: string;
  room_name: string | null; change: string | null; warning: string | null; attendance?: string;
}
interface Schedule {
  from: string;
  lessons: Lesson[];
  rooms: {room_name:string; lessons:number; minutes:number}[];
  workload: {teacher_name:string; lessons:number; minutes:number}[];
  attendance: {expected:number; finalized:number; draft:number; missing:number};
  examinations: {date:string; name:string; subject:string; room:string; starts_at:string; ends_at:string}[];
}
const field = (key: string, label: string, type = 'text'): Field => ({key,label,type,required:true});
const optional = (key: string, label: string, type = 'text'): Field => ({key,label,type});
const select = (key: string, label: string, lookup: string, required = true): Field =>
  ({key,label,lookup,required});
const choice = (key:string,label:string,values:[string,string][]): Field =>
  ({key,label,options:values,initial:values[0]![0],required:true});
const toggle = (key:string,label:string,initial:boolean): Field => ({key,label,type:'checkbox',initial});
const hours = [field('starts_at','Starts at','time'),field('ends_at','Ends at','time')];
const codes = [field('name','Name'),field('code','Code')];
const dates = [field('effective_start','Effective from','date'),field('effective_end','Effective through','date')];
const forms: Record<string, Field[]> = {
  settings: [toggle('separate_approver','Require a separate reviewer',true),toggle('enforce_capacity','Check room capacity',true)],
  shifts: [...codes,...hours,{...field('weekdays','Working weekdays (Mon=0, Sun=6)'),initial:'0,1,2,3,4'}],
  periods: [...codes,select('shift','Shift','shifts'),...hours,toggle('teaching','Teaching period',true)],
  rooms: [...codes,choice('kind','Room type',[['classroom','Classroom'],['laboratory','Laboratory'],['hall','Hall']]),optional('capacity','Capacity','number')],
  'teacher-availability': [select('teacher','Teacher','teachers'),field('weekday','Weekday (Monday = 0)','number'),
    ...hours,...dates,choice('preference','Constraint or preference',[['hard','Hard unavailability'],
      ['prefer','Preferred time'],['avoid','Non-preferred time']]),field('priority','Priority','number'),optional('reason','Reason')],
  'workload-policies': [select('teacher','Teacher','teachers'),...dates,
    optional('daily_max','Maximum periods per day','number'),optional('weekly_max','Maximum periods per week','number'),
    optional('consecutive_max','Maximum consecutive periods','number'),optional('rest_minutes','Minimum rest minutes','number'),
    toggle('hard','Enforce hard limit',true)],
  'teaching-groups': [...codes,select('session','Academic session','sessions'),select('section','Class and section','sections'),
    select('subject','Optional subject','subjects'),optional('capacity','Group capacity','number')],
  plans: [select('session','Academic session','sessions'),select('section','Class and section','sections'),
    select('shift','Shift','shifts'),...dates],
  'new-version': dates,
  'subject-requirements': [select('session','Academic session','sessions'),select('section','Class and section','sections'),
    select('subject','Subject','subjects'),field('minimum','Minimum lessons','number'),field('maximum','Maximum lessons','number')],
  entries: [choice('weekday','Day',[['0','Monday'],['1','Tuesday'],['2','Wednesday'],['3','Thursday'],['4','Friday'],['5','Saturday'],['6','Sunday']]),
    select('period','Teaching period','periods'),select('subject','Subject','subjects'),select('teacher','Teacher','teachers'),
    select('room','Room','rooms',false),select('group','Optional teaching group','teaching-groups',false),optional('notes','Notes')],
  exceptions: [select('entry','Scheduled lesson','daily'),field('date','Exception date','date'),
    choice('kind','Change',[['cancelled','Cancel'],['substitute','Substitute'],['rescheduled','Reschedule']]),
    optional('destination_date','Destination date','date'),
    select('teacher','Replacement teacher','teachers',false),select('period','Replacement period','periods',false),
    select('room','Replacement room','rooms',false),field('reason','Reason')],
};

@Component({
  imports:[FormsModule,ReactiveFormsModule,MatButtonModule,RouterLink],
  templateUrl:'./timetable-page.html',
  styleUrl:'./timetable-page.scss',
})
export class TimetablePage {
  private readonly api = inject(AdminApi);
  private readonly workspace = inject(AcademicWorkspace);
  readonly auth = inject(AuthService);
  readonly state = new RequestState();
  readonly lists = signal<Record<string,Row[]>>({});
  readonly schedule = signal<Schedule | null>(null);
  readonly day = new Date().toLocaleDateString('en-CA');
  date = this.day;
  section = '';
  teacher = '';
  room = '';
  weekly = true;
  tab = 'schedule';
  action = '';
  fields: Field[] = [];
  form = recordForm([]);
  editing = '';
  currentPlan = '';
  currentVersion = '';
  reviewReason = '';
  readonly versions = signal<Row[]>([]);
  readonly entries = signal<Row[]>([]);
  readonly tabs = [['schedule','Published schedule'],['plans','Plans and revisions'],['settings','Configuration'],['exceptions','Daily changes'],['reports','Reports']];
  readonly configuration = [['settings','Settings'],['shifts','Shifts'],['periods','Periods and breaks'],
    ['rooms','Rooms'],['teacher-availability','Teacher availability and preferences'],
    ['workload-policies','Teacher workload policies'],['teaching-groups','Optional teaching groups'],
    ['subject-requirements','Weekly subject requirements']];

  constructor() {
    void this.workspace.refresh();
    if (this.admin()) void this.state.run(async () => {
      await this.loadLookups();
      await this.loadSchedule();
    });
    else void this.state.run(() => this.loadSchedule());
  }

  admin() { return this.auth.has('accounts.view_timetable'); }
  can(grant: string) { return this.workspace.can('timetables','accounts.' + grant); }
  private read<T>(path: string, params: Record<string,string|number> = {}) {
    return this.api.read<T>('timetables/' + path, params);
  }
  private write<T>(path: string, method = 'POST', data?: unknown) {
    return this.api.write<T>(method, 'timetables/' + path, data);
  }
  readonly memberOptions = signal<Row[]>([]);
  selectedMembers: string[] = [];
  readonly previewWarnings = signal<string[]>([]);
  readonly reports = ['class','section','teacher-weekly','teacher-daily','rooms','workload','allocations',
    'unassigned','conflicts','substitutions','cancellations','reschedules','revisions','attendance'];
  report = 'section';
  reportThrough = '';
  reportSession = '';
  reportClass = '';
  reportSubject = '';
  reportGroup = '';
  reportStatus = '';
  reportOffset = 0;
  readonly reportData = signal<Page<Row> | null>(null);

  readonly allocation = signal<Row[]>([]);
  readonly suggestions = signal<Row[]>([]);
  private async loadLookups() {
    const local = ['shifts','periods','rooms','plans','teacher-availability','exceptions','subject-requirements','workload-policies','teaching-groups'];
    const lookup = ['sessions','sections','subjects','classes'];
    const identity = await Promise.all(local.map(async key => [key,(await this.read<Page<Row>>(key + '/', {limit:100})).results] as const));
    const academic = await Promise.all(lookup.map(async key => [key,
      this.auth.has('accounts.view_' + key) ? (await this.api.read<Page<Row>>((key === 'sessions' ? 'academic-sessions' : key) + '/', {limit:100})).results : []] as const));
    this.lists.set(Object.fromEntries([...identity,...academic,['teachers',await this.read<Row[]>('teachers/')]]));
  }

  filters() {
    return {date:this.date,...(this.section ? {section:this.section} : {}),
      ...(this.teacher ? {teacher:this.teacher} : {}),...(this.room ? {room:this.room} : {})};
  }
  async loadSchedule() {
    const result = await this.read<Schedule>(this.weekly ? 'weekly/' : 'daily/',this.filters());
    this.schedule.set(result);
  }
  exportUrl() { return '/api/v1/timetables/reports/export/?' + new URLSearchParams(this.filters()); }
  print() { window.print(); }
  setTab(tab: string) {
    this.tab = tab;
    this.action = '';
  }
  label(key: string, id: unknown) {
    const row = this.lists()[key]?.find(option => option['id'] === id);
    if (!row) return id ?? '—';
    if (key === 'periods' && row['teaching'] === false) return row['name'] + ' (break)';
    const prefix = key === 'sections' ? this.lists()['classes']?.find(item => item['id'] === row['academic_class'])?.['name'] : null;
    return [prefix,row['name'] ?? row['code']].filter(Boolean).join(' · ');
  }
  activeVersion() { return this.versions().find(row => row['id'] === this.currentVersion); }
  pickPlan(plan: Row) {
    this.action = '';
    return this.state.run(async () => {
      this.currentPlan = String(plan['id']);
      this.currentVersion = '';
      this.versions.set([]);
      this.entries.set([]);
      this.allocation.set([]);
      this.versions.set(await this.read<Row[]>('plans/' + this.currentPlan + '/versions/'));
      await this.loadEntries(String(this.versions()[0]?.['id'] ?? ''));
    });
  }
  async loadEntries(id: string) {
    this.currentVersion = id;
    const [entries,allocation] = await Promise.all(id ? [
      this.read<Page<Row>>('entries/',{version:id,limit:100}).then(rows => rows.results),
      this.read<Row[]>('plans/' + this.currentPlan + '/subject-allocation/', {version:id}),
    ] : [[],[]]);
    this.entries.set(entries);
    this.allocation.set(allocation);
  }

  options(key: string): Row[] {
    if (key === 'group-members') return this.memberOptions();
    if (key === 'daily') return (this.schedule()?.lessons ?? []).filter(row => row.date === this.date && !row.change)
      .map(row => ({id:row.entry,name:[row.section_name,row.period,row.subject_name].join(' · ')}));
    return this.lists()[key] ?? [];
  }
  readonly lessonOptions = signal<{subjects:Row[]; teachers:Row[]; groups:Row[]}>({
    subjects:[], teachers:[], groups:[],
  });
  readonly lessonOptionsLoading = signal(false);
  readonly lessonOptionsError = signal(false);
  private lessonOptionsRequest = 0;

  editorOptions(key: string) {
    if (this.action === 'entries') {
      const options = this.lessonOptions();
      if (key === 'subjects') return options.subjects;
      if (key === 'teachers') return options.teachers;
      if (key === 'teaching-groups') return options.groups;
    }
    return this.options(key);
  }

  editorSelectionChanged(key: string) {
    if (this.action === 'teaching-groups' && ['session','section'].includes(key)) {
      void this.loadGroupMembers();
    }
    if (this.action !== 'entries' || !['weekday','period','subject'].includes(key)) return;
    if (key === 'subject') this.form.patchValue({teacher:'',group:''});
    else this.previewWarnings.set([]);
    void this.refreshLessonOptions();
  }

  async refreshLessonOptions() {
    const request = ++this.lessonOptionsRequest;
    const form = this.form;
    const {weekday,period,subject} = form.getRawValue();
    this.lessonOptionsLoading.set(true);
    this.lessonOptionsError.set(false);
    try {
      const result = await this.read<{subjects:Row[]; teachers:Row[]; groups:Row[]}>(
        'plans/' + this.currentPlan + '/lesson-options/', {
          version:this.currentVersion, weekday:String(weekday),
          ...(period ? {period:String(period)} : {}),
          ...(subject ? {subject:String(subject)} : {}),
        });
      if (request !== this.lessonOptionsRequest || this.action !== 'entries' || form !== this.form) return;
      this.lessonOptions.set(result);
      for (const [field, allowed] of [['subject', result.subjects], ['teacher', result.teachers],
        ['group', result.groups]] as const) {
        const control = form.controls[field];
        if (control?.value && !allowed.some(row => row['id'] === control.value)) control.setValue('');
      }
    } catch {
      if (request === this.lessonOptionsRequest) {
        this.lessonOptions.set({subjects:[], teachers:[], groups:[]});
        this.lessonOptionsError.set(true);
      }
    } finally {
      if (request === this.lessonOptionsRequest) this.lessonOptionsLoading.set(false);
    }
  }

  open(key: string, row?: Row) {
    this.action = key;
    this.suggestions.set([]);
    this.previewWarnings.set([]);
    const members = row?.['enrollments'];
    this.selectedMembers = Array.isArray(members) ? members.map(String) : [];
    this.fields = forms[key] ?? [];
    this.form = recordForm(this.fields);
    this.editing = row ? String(row['id'] ?? '') : '';
    if (row) for (const item of this.fields) {
      const value = row[item.key];
      this.form.controls[item.key]?.setValue(Array.isArray(value) ? value.join(',') : value ?? '');
    }
    if (key === 'entries') {
      this.lessonOptions.set({subjects:[],teachers:[],groups:[]});
      void this.refreshLessonOptions();
    }
    if (key === 'teacher-availability' && !row) this.form.controls['priority']?.setValue(1);
    if (key === 'teaching-groups' && row) void this.loadGroupMembers();
    if (key === 'exceptions') this.form.controls['date']?.setValue(this.date);
    if (key === 'settings') void this.state.run(async () => this.form.patchValue(await this.read<Row>('settings/')));
  }

  async loadGroupMembers() {
    const {section,session} = this.form.getRawValue();
    this.memberOptions.set([]);
    if (!section || !session || !this.auth.has('accounts.view_students')) return;
    await this.state.run(async () => {
      const options: Row[] = [];
      for (let offset = 0; ; offset += 50) {
        const data = await this.read<Page<Row>>('group-members/',{section:String(section),session:String(session),offset,limit:50});
        options.push(...data.results);
        if (!data.next) break;
      }
      this.memberOptions.set(options);
    });
  }

  reportFilters() {
    return {...this.filters(),...(this.reportThrough ? {through:this.reportThrough} : {}),
      ...(this.reportSession ? {session:this.reportSession} : {}),
      ...(this.reportClass ? {academic_class:this.reportClass} : {}),
      ...(this.reportSubject ? {subject:this.reportSubject} : {}),
      ...(this.reportGroup ? {group:this.reportGroup} : {}),
      ...(this.reportStatus ? {status:this.reportStatus} : {})};
  }
  runReport(offset=0) {
    this.reportPrint.set(null);
    return this.state.run(async () => {
      const data = await this.read<Page<Row>>('reports/' + this.report + '/',
        {...this.reportFilters(),offset});
      this.reportOffset = offset;
      this.reportData.set(data);
    });
  }
  readonly reportPrint = signal<{title:string; from:string; through:string; scope:string[]; rows:Row[]} | null>(null);

  async printReport() {
    this.reportPrint.set(null);
    const report = this.report;
    const through = this.reportThrough;
    const filters = this.reportFilters();
    const scope = [
      ['sessions', this.reportSession], ['classes', this.reportClass], ['sections', this.section],
      ['teachers', this.teacher], ['rooms', this.room], ['subjects', this.reportSubject],
      ['teaching-groups', this.reportGroup],
    ].filter(([, id]) => !!id).map(([key, id]) => String(this.label(key!, id)));
    const ready = await this.state.run(async () => {
      const rows: Row[] = [];
      for (let offset = 0; ; offset += 100) {
        const page = await this.read<Page<Row>>('reports/' + report + '/',
          {...filters, limit:100, offset});
        rows.push(...page.results);
        if (!page.next || !page.results.length) break;
      }
      this.reportPrint.set({
        title:report.replaceAll('-', ' '), from:filters.date, through, scope, rows,
      });
    });
    if (ready) requestAnimationFrame(() => this.print());
  }

  reportExport() {
    return '/api/v1/timetables/reports/' + this.report + '/?' +
      new URLSearchParams({...this.reportFilters(),format_type:'csv'});
  }
  reportColumns(row:Row) {
    return Object.keys(row).filter(key => !['entry','teacher','subject','room','group','academic_class'].includes(key));
  }
  inactive(lesson: Lesson) { return lesson.change === 'cancelled' || lesson.change === 'rescheduled_out'; }

  private payload() {
    const data = this.form.getRawValue();
    if (this.action === 'entries') data['version'] = this.currentVersion;
    const payload: Record<string,unknown> = Object.fromEntries(Object.entries(data).map(([key,value]) => [key,value === '' && ['room','teacher','period','capacity','group','destination_date','daily_max','weekly_max','consecutive_max'].includes(key) ? null : value]));
    if (this.action === 'workload-policies' && !payload['rest_minutes']) payload['rest_minutes'] = 0;
    if (this.action === 'teaching-groups' && this.auth.has('accounts.view_students')) payload['enrollments'] = this.selectedMembers;
    if (this.action === 'shifts') payload['weekdays'] = String(data['weekdays']).split(',').map(day => Number(day.trim()));
    return payload;
  }
  async save() {
    if (!this.action || this.form.invalid || this.state.loading() || this.lessonEditorBlocked()) return;
    const key = this.action;
    const plan = this.currentPlan;
    const path = key === 'new-version' ? 'plans/' + plan + '/new-version/' : key + '/' + (this.editing ? this.editing + '/' : '');
    const ok = await this.state.run(async () => {
      const result = await this.write<Row>(path,this.editing || key === 'settings' ? 'PATCH' : 'POST',this.payload());
      await this.loadLookups();
      if (key === 'plans') {
        this.currentPlan = String(result['id']);
        this.versions.set(await this.read<Row[]>('plans/' + this.currentPlan + '/versions/'));
        await this.loadEntries(String(this.versions()[0]?.['id'] ?? ''));
      } else if (key === 'new-version') {
        this.versions.set(await this.read<Row[]>('plans/' + plan + '/versions/'));
        await this.loadEntries(String(result['id']));
      } else if (key === 'entries') await this.loadEntries(this.currentVersion);
      else if (key === 'exceptions') await this.loadSchedule();
    },'Timetable change saved.');
    if (ok) this.action = '';
  }

  findSlots() {
    const fields = this.form.getRawValue();
    if (!fields['subject'] || !fields['teacher']) return;
    const params = {version:this.currentVersion,subject:String(fields['subject']),teacher:String(fields['teacher']),
      ...(fields['room'] ? {room:String(fields['room'])} : {}),...(fields['group'] ? {group:String(fields['group'])} : {})};
    return this.state.run(async () => this.suggestions.set(await this.read<Row[]>('suggestions/',params)));
  }

  applySlot(row: Row) {
    this.form.patchValue({weekday:String(row['weekday']),period:String(row['period'])});
    void this.refreshLessonOptions();
  }

  lessonEditorBlocked() {
    if (this.action !== 'entries') return false;
    if (this.lessonOptionsLoading() || this.lessonOptionsError()) return true;
    const values = this.form.getRawValue();
    const options = this.lessonOptions();
    if (values['subject'] && !options.subjects.some(row => row['id'] === values['subject'])) return true;
    if (values['teacher'] && !options.teachers.some(row => row['id'] === values['teacher'])) return true;
    if (values['group'] && !options.groups.some(row => row['id'] === values['group'])) return true;
    if (options.groups.length && !values['group']) return true;
    return false;
  }

  validate() {
    if (this.form.invalid || this.lessonEditorBlocked()) return;
    return this.state.run(async () => {
      const result = await this.write<{warnings:string[];preference_score:number}>('validate/','POST',this.payload());
      this.previewWarnings.set([...result.warnings,...(result.preference_score < 0 ? ['Non-preferred teaching time'] : [])]);
    },
      'The lesson has no scheduling conflicts.');
  }

  canCreateRosterSuccessor(row: Row) {
    const group = this.options('teaching-groups').find(item => item['id'] === row['group']);
    return group && String(this.activeVersion()?.['effective_start'] ?? '') > this.day &&
      this.versions().some(version => version['status'] === 'published') &&
      group['effective_version'] !== this.currentVersion &&
      this.auth.has('accounts.view_students') &&
      this.entries().find(entry => entry['group'] === row['group']) === row;
  }

  async createRosterSuccessor(row: Row) {
    if (!await this.api.confirm('Create a successor roster for this future draft?')) return;
    const version = this.currentVersion;
    const created = await this.state.run(async () => {
      await this.write('teaching-groups/' + row['group'] + '/successor/', 'POST', {version});
      await this.loadLookups();
      await this.loadEntries(version);
    }, 'Draft successor roster created. Edit its membership before submitting.');
    if (created) this.setTab('settings');
  }

  async remove(row: Row) {
    if (!await this.api.confirm('Remove this draft lesson?')) return;
    await this.state.run(async () => {
      await this.write('entries/' + row['id'] + '/','DELETE');
      await this.loadEntries(this.currentVersion);
    },'Draft lesson removed.');
  }

  async transition(action: string) {
    const version = this.activeVersion();
    if (!version || this.state.loading() || !await this.api.confirm('Confirm timetable ' + action + '?')) return;
    const expected = action === 'publish' ? version['approved_at'] : version['submitted_at'];
    await this.state.run(async () => {
      await this.write('plans/' + this.currentPlan + '/' + action + '/','POST',{
        version:version['id'],reason:this.reviewReason,
        ...(action !== 'submit' && expected ? {expected_decision_at:expected} : {}),
      });
      this.versions.set(await this.read<Row[]>('plans/' + this.currentPlan + '/versions/'));
      this.reviewReason = '';
      await this.loadSchedule();
    },'Timetable ' + action + ' recorded.');
  }

  readonly weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
  draftLessons(weekday:number) { return this.entries().filter(row => row['weekday'] === weekday); }
  refreshSchedule() { return this.state.run(() => this.loadSchedule()); }
  chooseVersion(id: string) { this.action = ''; return this.state.run(() => this.loadEntries(id)); }
  editorTitle() {
    const headings: Record<string,string> = {plans:'New timetable plan',entries:'Teaching lesson',
      'new-version':'New timetable revision',exceptions:'Dated schedule exception'};
    return headings[this.action] ?? (this.configuration.find(item => item[0] === this.action)?.[1] ?? 'Timetable settings');
  }

  dates() {
    return [...new Set(this.schedule()?.lessons.map(row => row.date) ?? [])];
  }
  lessons(date: string) { return this.schedule()?.lessons.filter(row => row.date === date) ?? []; }
}
