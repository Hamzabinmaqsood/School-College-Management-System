import { Component, HostListener, inject, signal } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, Field, Value, recordForm } from './academic-tools';
import { AuthService } from './auth';
import { examFields, examPages, nestedFields } from './exam-config';

type Entry = Record<string, unknown>;
export function markUnits(value: string | null) {
  if (!value || !/^\d{1,8}(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole!) * 100n + BigInt(fraction.padEnd(2, '0'));
}
interface Mark {registration: string; student: string; admission: string; roll: string; status: string; obtained: string | null; remarks: string}
interface Submission {id: string; version: number; status: string; maximum: string; marks: Mark[]}

@Component({imports:[FormsModule, ReactiveFormsModule, RouterLink, MatButtonModule], templateUrl:'./exam-page.html'})
export class ExamPage {
  readonly auth = inject(AuthService);
  readonly api = inject(AdminApi);
  readonly workspace = inject(AcademicWorkspace);
  readonly state = new RequestState();
  readonly page = inject(ActivatedRoute).snapshot.data['examPage'] as string;
  readonly config = examPages[this.page]!;
  readonly menu = Object.entries(examPages);
  readonly resource = ({overview:'exams', create:'exams', grading:'grading-schemes',
    review:'marks', settings:'registrations'} as Record<string,string>)[this.page] ?? this.page;
  readonly fields = examFields[this.resource] ?? [];
  readonly nested = nestedFields[this.resource] ?? [];
  readonly form = recordForm(this.fields);
  readonly lines = signal([recordForm(this.nested)]);
  readonly rows = signal<Entry[]>([]);
  readonly choices = signal<Record<string, Entry[]>>({});
  readonly submission = signal<Submission | null>(null);
  readonly result = signal<Entry | null>(null);
  readonly editing = signal('');
  readonly changed = signal(false);
  readonly statuses = ['missing','marked','absent','excused','exempt','withheld'];
  readonly reports = ['class-results','subject-marks','subject-performance','pass-fail','grade-distribution',
    'examination-summary','high-achievers','support','history',
    ...(this.auth.has('accounts.scope_all_examinations') && this.auth.has('accounts.view_exam_marks') ? ['completion','submissions'] : [])];
  readonly markFilters: Record<string, string> = {};
  readonly markFilterFields = [
    ['component__subject__group__exam__session','Session'], ['component__subject__group__exam','Exam'],
    ['component__subject__group__academic_class','Class'], ['section','Section'],
    ['component__subject__subject','Subject'], ['component','Component'],
  ];
  readonly filters = {exam:'', session:'', academic_class:'', section:'', subject:''};
  report = 'class-results';
  search = '';
  reason = '';
  readonly revisionForm = recordForm([
    {key:'component', label:'Component', required:true}, {key:'status', label:'Status', initial:'marked'},
    {key:'obtained', label:'Obtained'}, {key:'remarks', label:'Remarks'}, {key:'reason',label:'Reason',required:true},
  ]);
  correcting = '';
  offset = 0;
  resultOffset = 0;
  count = 0;

  constructor() {
    void this.workspace.refresh();
    if (this.page === 'settings') {
      this.form.controls['group']?.valueChanges.subscribe(() => {
        void this.state.run(() => this.loadEnrollmentChoices());
      });
    }
    void this.state.run(async () => {
      await this.load();
      await this.loadChoices();
    });
  }

  can(permission: string) { return this.workspace.can('examinations', permission); }

  async loadChoices() {
    if (this.resource === 'marks') {
      this.choices.set(await this.api.read<Record<string, Entry[]>>('examinations/marks/lookups/'));
      return;
    }
    const data: Record<string, Entry[]> = {};
    const paths = new Set(this.fields.flatMap(field => field.lookup ? [field.lookup] : []));
    paths.delete('enrollments');
    if (this.page === 'reports') for (const path of ['exams','academic-sessions','classes','sections','subjects']) paths.add(path);
    if (paths.has('exam-classes')) { paths.add('exams'); paths.add('classes'); }
    await Promise.all([...paths].map(async path => {
      const endpoint = path === 'exam-classes' ? 'examinations/classes' :
        path === 'exam-subjects' ? 'examinations/subjects' :
        ['academic-sessions','classes','sections','subjects'].includes(path) ? path : 'examinations/' + path;
      data[path] = (await this.api.read<Page<Entry>>(endpoint + '/', {limit:100})).results;
    }));
    this.choices.set(data);
  }

  name(row: Entry) {
    const related = this.choices()['classes']?.find(item => item['id'] === row['academic_class']);
    const exam = this.choices()['exams']?.find(item => item['id'] === row['exam']);
    return row['name'] ?? row['subject_name'] ?? (related ? String(related['name']) + ' · ' + (exam?.['name'] ?? '') : row['id']);
  }

  async loadEnrollmentChoices() {
    const group = this.form.controls['group']?.value;
    if (!group) return;
    this.form.controls['enrollment']?.setValue('');
    this.form.controls['optional_subjects']?.setValue('');
    const data = await this.api.read<{enrollments: Entry[]; subjects: Entry[]}>(
      'examinations/registrations/choices/', {group: String(group), search:this.search, limit:100});
    this.choices.update(previous => ({...previous, enrollments:data.enrollments, optional:data.subjects}));
  }

  optionalChecked(item: Entry) {
    return String(this.form.controls["optional_subjects"]?.value ?? "").split(",").includes(String(item["id"]));
  }

  refreshEnrollmentChoices() { return this.state.run(() => this.loadEnrollmentChoices()); }

  chooseOptional(item: Entry, checked: boolean) {
    const id = String(item['id']);
    const control = this.form.controls['optional_subjects'];
    const values = String(control?.value ?? '').split(',').filter(Boolean);
    control?.setValue((checked ? [...values, id] : values.filter(value => value !== id)).join(','));
  }

  options(field: Field) { return this.choices()[field.lookup ?? ''] ?? []; }

  params() { return Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value)); }
  get endpoint() { return 'examinations/' + (this.page === 'reports' ? 'reports/' + this.report : this.resource) + '/'; }

  async load(offset = 0) {
    const report = this.page === 'reports';
    const params = {...(report ? this.params() : {...Object.fromEntries(Object.entries(this.markFilters).filter(([, value]) => value)), search:this.search}), offset, limit:25};
    const result = await this.api.read<Page<Entry>>(this.endpoint, params);
    this.rows.set(result.results);
    this.offset = offset;
    this.count = result.count;
  }

  reload(offset = 0) { return this.state.run(() => this.load(offset)); }

  formPayload() {
    const data: Entry = this.form.getRawValue();
    if (data['scheme'] === '') data['scheme'] = null;
    if (this.resource === 'registrations') data['optional_subjects'] = String(data['optional_subjects']).split(',')
      .map(value => value.trim()).filter(Boolean);
    if (this.nested.length) {
      const key = this.resource === 'subjects' ? 'components' : 'bands';
      data[key] = this.lines().map(line => Object.fromEntries(Object.entries(line.getRawValue())
        .filter(([, value]) => value !== '')));
    }
    return data;
  }

  async save() {
    if (this.form.invalid || this.lines().some(line => line.invalid)) return;
    const id = this.editing();
    await this.state.run(async () => {
      const data = await this.api.write<Entry>(id ? 'PATCH' : 'POST',
        this.endpoint + (id ? id + '/' : ''), this.formPayload());
      if (this.resource === 'results') await this.open(data);
      this.editing.set('');
      this.form.reset(recordForm(this.fields).getRawValue());
      this.lines.set([recordForm(this.nested)]);
      await this.load();
    }, this.resource === 'results' ? 'Draft results calculated.' : 'Record saved.');
  }

  edit(row: Entry) {
    this.editing.set(String(row['id']));
    if (this.resource === 'subjects') {
      this.lines.set((row['components'] as Record<string, Value>[]).map(item => recordForm(this.nested, item)));
    }
    this.form.reset(Object.fromEntries(this.fields.map(field => [
      field.key, (row[field.key] ?? field.initial ?? '') as Value,
    ])));
  }

  async run(row: Entry, action: string, body: Entry = {}) {
    if (!await this.api.confirm('Confirm ' + action + '?')) return;
    await this.state.run(async () => {
      const data = await this.api.write<Entry>('POST', this.endpoint + row['id'] + '/' + action + '/', body);
      if (this.page === 'results') await this.open(data);
      await this.load(this.offset);
    }, 'Change recorded.');
  }

  resultRows(record: Entry) { return (record["results"] as Page<Entry>).results; }
  invalid(record: Submission) { return record.marks.some(row => !this.valid(row)); }
  moreResults(record: Entry, delta: number) {
    return this.state.run(async () => {
      const offset = this.resultOffset + delta;
      this.result.set(await this.api.read<Entry>(this.endpoint + record["id"] + "/", {offset, limit:25}));
      this.resultOffset = offset;
    });
  }
  async open(row: Entry) {
    if (this.page === 'results') {
      this.resultOffset = 0;
      this.result.set(await this.api.read<Entry>(this.endpoint + row['id'] + '/'));
    } else {
      this.submission.set(await this.api.read<Submission>(this.endpoint + row['id'] + '/'));
      this.changed.set(false);
    }
  }

  async select(row: Entry) {
    if (!await this.leave()) return;
    await this.state.run(() => this.open(row));
  }

  @HostListener('window:beforeunload', ['$event'])
  warn(event: BeforeUnloadEvent) {
    if (this.changed()) { event.preventDefault(); event.returnValue = ''; }
  }

  leave() { return !this.changed() || this.api.confirm('Discard unsaved marks?'); }

  updateMark(row: Mark, key: 'obtained'|'status'|'remarks', value: string) {
    row[key] = value;
    if (key === 'status' && value !== 'marked') row.obtained = null;
    if (key === 'obtained' && value) row.status = 'marked';
    this.changed.set(true);
  }

  valid(row: Mark) {
    if (row.status !== 'marked') return true;
    const mark = markUnits(row.obtained);
    const maximum = markUnits(this.submission()?.maximum ?? null);
    return mark !== null && maximum !== null && mark <= maximum;
  }

  async marksAction(action: string) {
    const current = this.submission();
    if (!current || this.state.loading()) return;
    if (action !== 'save' && !await this.api.confirm('Confirm ' + action + '?')) return;
    const body = action === 'save' ? {version:current.version, marks:current.marks.map(row => ({
      registration:row.registration, status:row.status, obtained:row.status === 'marked' ? row.obtained : null,
      remarks:row.remarks,
    }))} : {version:current.version, ...(action === "return" && {reason:this.reason})};
    const saved = await this.state.run(async () => {
      const data = await this.api.write<Submission>('POST', this.endpoint + current.id + '/' + action + '/', body);
      this.submission.set(data);
      this.changed.set(false);
      await this.load(this.offset);
    }, 'Marks workflow updated.');
    if (saved) this.reason = '';
  }

  correctionOptions(row: Entry) {
    return (row['corrections'] ?? []) as {registration: string; component: string; name: string}[];
  }

  async correct(record: Entry, row: Entry) {
    const values = this.revisionForm.getRawValue();
    const target = this.correctionOptions(row).find(option => option.component === values['component']);
    if (!target || this.revisionForm.invalid || !await this.api.confirm('Record a correction and recalculate?')) return;
    await this.state.run(async () => {
      const response = await this.api.write<Entry>('POST', this.endpoint + record['id'] + '/correct/', {
        ...values, registration: target.registration,
        obtained: values['status'] === 'marked' ? values['obtained'] : null,
      });
      await this.open(response);
      await this.load();
      this.correcting = '';
    }, 'Correction recorded. Review the new draft revision.');
  }

  columns(row: Entry) {
    return Object.keys(row).filter(key => !['id','created_at','updated_at','bands','components'].includes(key));
  }
  label(value: string) { return value.replaceAll('_',' ').replaceAll('-',' '); }
  printLink() { return '/api/v1/' + this.endpoint + 'export/?' + new URLSearchParams(this.params()).toString(); }
  addLine() { this.lines.update(rows => [...rows, recordForm(this.nested)]); }
  removeLine(index: number) { this.lines.update(rows => rows.filter((_, position) => index !== position)); }
}
