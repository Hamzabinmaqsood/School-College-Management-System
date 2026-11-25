import { Component, HostListener, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, Row } from './academic-tools';
import { AuthService } from './auth';
import { attendanceMonth } from "./attendance-calendar";

export const marks = ['unmarked', 'present', 'absent', 'late', 'excused'];
interface Group {
  session: string; session_name: string; academic_class: string; class_name: string;
  section: string | null; section_name: string | null; subject: string | null; subject_name: string | null;
}
interface Mark {
  id: string; student_name: string; admission_number: string; roll_number: string;
  status: string; remarks: string; approved_leave: boolean;
  corrections?: {id: string; previous_status: string; status: string; reason: string; at: string}[];
}
interface Register {
  id: string; status: string; date: string; mode: string; version: number; records: Mark[];
  class_name: string; section_name?: string; subject_name?: string; period?: string;
  schedule_snapshot?: {entry?:string; period?:string; starts_at?:string; ends_at?:string};
}
interface Roster {
  register: Register | null; working_day?: boolean; reserved?: number;
  roster: {student: string; student_name: string; admission_number: string; roll_number: string}[];
}
interface Context { broad: boolean; primary_mode: string; date: string; assignments: Group[] }

@Component({
  imports: [FormsModule, RouterLink, MatButtonModule],
  templateUrl: './attendance-page.html',
})
export class AttendancePage {
  readonly api = inject(AdminApi);
  readonly auth = inject(AuthService);
  readonly workspace = inject(AcademicWorkspace);
  readonly state = new RequestState();
  readonly context = signal<Context | null>(null);
  readonly sessions = signal<Row[]>([]);
  readonly classes = signal<Row[]>([]);
  readonly sections = signal<Row[]>([]);
  readonly subjects = signal<Row[]>([]);
  readonly roster = signal<Roster | null>(null);
  loadedCriteria: ReturnType<AttendancePage["criteria"]> = null;
  readonly register = signal<Register | null>(null);
  readonly history = signal<Register[]>([]);
  readonly marks = marks;
  readonly Object = Object;
  private readonly route = inject(ActivatedRoute);
  readonly isHistory = this.route.snapshot.data['history'] === true;
  readonly id = this.route.snapshot.queryParamMap.get('register');
  readonly edits = signal<Record<string, {status: string; remarks: string}>>({});
  group = '';
  historyRange = {from_date: '', to_date: '', mode: '', search: ''};
  historyMonth = '';

  showMonth() {
    const dates = attendanceMonth(this.historyMonth);
    if (!dates) return;
    this.filter.date = '';
    this.historyRange = {...this.historyRange, ...dates};
    return this.loadHistory();
  }
  historyOffset = 0;
  readonly historyCount = signal(0);
  filter = {date: '', session: '', academic_class: '', section: '', mode: 'daily', subject: '', period: '',
    start_time: '', end_time: ''};
  bulkMark = 'present';
  overrideReason = '';
  reason = '';
  correction = '';
  correctedStatus = 'present';
  correctedRemarks = '';

  constructor() {
    void this.workspace.refresh();
    if (this.isHistory) { void this.loadHistory(); return; }
    if (this.id) { void this.state.run(() => this.select(this.id!)); return; }
    void this.state.run(async () => {
      const context = await this.api.read<Context>('attendance/groups/');
      this.context.set(context);
      this.filter.mode = context.primary_mode;
      this.filter.date = context.date;
      if (context.broad) {
        const {sessions, classes, sections, subjects} = await this.api.read<{
          sessions: Row[]; classes: Row[]; sections: Row[]; subjects: Row[];
        }>('attendance/lookups/');
        this.sessions.set(sessions);
        this.classes.set(classes);
        this.sections.set(sections);
        this.subjects.set(subjects);
        this.filter.session = sessions.find(row => row['is_current'])?.id ?? '';
      }
      const query = this.route.snapshot.queryParamMap;
      const date = query.get('date');
      const period = query.get('period');
      if (date && period) {
        const session = query.get('session') ?? '';
        const academic_class = query.get('academic_class') ?? '';
        const section = query.get('section') ?? '';
        const subject = query.get('subject') ?? '';
        const index = context.assignments.findIndex(row =>
          row.session === session && row.academic_class === academic_class && row.section === section && row.subject === subject);
        if (context.broad || index >= 0) {
          this.filter = {...this.filter,date,period,session,academic_class,section,subject,mode:'period'};
          if (!context.broad) this.group = String(index);
        }
      }
    });
  }

  can(permission: string) { return this.workspace.can('attendance', permission); }

  @HostListener('window:beforeunload', ['$event'])
  warn(event: BeforeUnloadEvent) {
    if (Object.keys(this.edits()).length) { event.preventDefault(); event.returnValue = ''; }
  }

  leave() {
    return !Object.keys(this.edits()).length || this.api.confirm('Discard unsaved attendance marks?');
  }

  async select(id: string) {
    this.setRegister(await this.api.read<Register>('attendance/' + id + '/'));
  }

  setRegister(register: Register | null) {
    this.register.set(register);
    this.edits.set({});
    this.correction = '';
  }

  async loadHistory(offset = 0) {
    await this.state.run(async () => {
      const filters = Object.fromEntries(Object.entries(this.historyRange).filter(([, value]) => value));
      const response = await this.api.read<Page<Register>>('attendance/history/', {
        ...filters, ...(this.filter.date && {date: this.filter.date}), limit: 30, offset,
      });
      this.history.set(response.results);
      this.historyCount.set(response.count);
      this.historyOffset = offset;
    });
  }

  criteria() {
    const group = this.context()?.assignments[Number(this.group)];
    const f = this.filter;
    if (!this.context()?.broad && (!this.group || !group)) return null;
    const session = this.context()?.broad ? f.session : group?.session;
    const academic_class = this.context()?.broad ? f.academic_class : group?.academic_class;
    const section = this.context()?.broad ? f.section : group?.section;
    const subject = this.context()?.broad ? f.subject : group?.subject;
    const mode = this.context()?.broad ? f.mode : (subject ? 'period' : 'daily');
    if (!session || !academic_class || !f.date || (mode === 'period' && (!subject || !f.period.trim()))) return null;
    return {session, academic_class, date: f.date, mode, ...(section && {section}),
      ...(mode === 'period' && {subject: subject!, period: f.period.trim()}),
      ...(mode === 'period' && f.start_time && {start_time: f.start_time}),
      ...(mode === 'period' && f.end_time && {end_time: f.end_time})};
  }

  async loadRoster() {
    const criteria = this.criteria();
    if (!criteria || !await this.leave()) return;
    await this.state.run(async () => {
      const data = await this.api.read<Roster>('attendance/roster/', criteria);
      this.roster.set(data);
      this.loadedCriteria = criteria;
      this.overrideReason = "";
      this.setRegister(data.register);
    });
  }

  async start() {
    const criteria = this.loadedCriteria;
    if (!criteria) return;
    await this.state.run(async () => {
      this.setRegister(await this.api.write<Register>('POST', 'attendance/', {
        ...criteria, calendar_override: this.overrideReason,
      }));
      this.roster.set(null);
    }, 'Draft created.');
  }

  mark(row: Mark) { return this.edits()[row.id] ?? row; }

  edit(row: Mark, change: Partial<{status: string; remarks: string}>) {
    this.edits.update(edits => ({...edits, [row.id]: {
      status: this.mark(row).status, remarks: this.mark(row).remarks, ...change,
    }}));
  }

  bulk(register: Register) {
    this.edits.set(Object.fromEntries(register.records.map(row => [row.id, {
      status: this.bulkMark, remarks: this.mark(row).remarks,
    }])));
  }

  async update(register: Register, action: string, data: object, message: string) {
    await this.state.run(async () => {
      const result = await this.api.write<Register>('POST', 'attendance/' + register.id + '/' + action + '/',
        {version: register.version, ...data});
      this.setRegister(result);
    }, message);
    void this.workspace.refresh();
  }

  save(register: Register) {
    return this.update(register, 'save', {marks: Object.entries(this.edits()).map(([record, mark]) => ({
      record, ...mark,
    }))}, 'Draft saved.');
  }

  async finalize(register: Register) {
    const unmarked = register.records.filter(row => row.status === 'unmarked').length;
    if (await this.api.confirm(unmarked ? 'Finalize with ' + unmarked + ' students unmarked?' : 'Finalize this register?')) {
      await this.update(register, 'finalize', {acknowledge_unmarked: unmarked > 0}, 'Register finalized.');
    }
  }

  beginCorrection(row: Mark) {
    this.correction = row.id;
    this.correctedStatus = row.status;
    this.correctedRemarks = row.remarks;
    this.reason = '';
  }

  correct(register: Register, row: Mark, useLeave = false) {
    return this.update(register, 'correct', {record: row.id, reason: this.reason, remarks: this.correctedRemarks,
      ...(useLeave ? {use_leave: true} : {status: this.correctedStatus})}, 'Correction recorded.');
  }
}
