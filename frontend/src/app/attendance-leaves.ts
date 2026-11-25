import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, Row } from './academic-tools';

interface Leave extends Row {
  status: string; start_date: string; end_date: string; student_name: string;
  class_name: string; reason: string; review_remarks: string;
}
interface Decision {id: string; status: string; remarks: string; created_at: string}
@Component({
  imports: [FormsModule, RouterLink, MatButtonModule],
  templateUrl: './attendance-leaves.html',
})
export class AttendanceLeaves {
  readonly api = inject(AdminApi);
  readonly workspace = inject(AcademicWorkspace);
  readonly state = new RequestState();
  readonly sessions = signal<Row[]>([]);
  readonly classes = signal<Row[]>([]);
  readonly students = signal<Row[]>([]);
  readonly requests = signal<Leave[]>([]);
  readonly selected = signal<(Leave & {decisions: Decision[]}) | null>(null);
  filters = {status: '', from_date: '', to_date: '', enrollment__academic_class: ''};
  search = '';
  remarks = '';
  draft = {session: '', student: '', start_date: '', end_date: '', reason: ''};

  constructor() {
    void this.workspace.refresh();
    void this.state.run(async () => {
      const [sessions, classes] = await Promise.all([
        this.api.read<Row[]>('attendance/leaves/sessions/'), this.api.read<Row[]>('attendance/leaves/classes/'),
        this.fetch(),
      ]);
      this.classes.set(classes);
      this.sessions.set(sessions);
      this.draft.session = sessions.find(row => row['is_current'])?.id ?? '';
    });
  }

  can(permission: string) { return this.workspace.can('attendance', permission); }

  async fetch() {
    const params = Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value));
    const result = await this.api.read<Page<Leave>>('attendance/leaves/', {...params, limit: 100});
    this.requests.set(result.results);
  }

  load() { return this.state.run(() => this.fetch()); }

  choices() {
    this.draft.student = '';
    this.students.set([]);
    if (!this.draft.session || !this.draft.start_date) return;
    void this.state.run(async () => {
      this.students.set((await this.api.read<Page<Row>>('attendance/leaves/choices/', {
        session: this.draft.session, date: this.draft.start_date, search: this.search, limit: 100,
      })).results);
    });
  }

  async submit() {
    await this.state.run(async () => {
      await this.api.write('POST', 'attendance/leaves/', this.draft);
      this.draft = {...this.draft, student: '', reason: ''};
      await this.fetch();
    }, 'Leave request submitted.');
    void this.workspace.refresh();
  }

  async get(id: string) {
    const data = await this.api.read<Leave & {decisions: Decision[]}>('attendance/leaves/' + id + '/');
    this.selected.set(data);
  }

  detail(id: string) {
    this.remarks = '';
    return this.state.run(() => this.get(id));
  }

  async decide(id: string, action: string) {
    if (!await this.api.confirm('Apply this leave decision?')) return;
    await this.state.run(async () => {
      await this.api.write('POST', 'attendance/leaves/' + id + '/' + action + '/', {remarks: this.remarks});
      this.remarks = '';
      await Promise.all([this.fetch(), this.get(id)]);
    }, 'Leave decision recorded.');
    void this.workspace.refresh();
  }
}
