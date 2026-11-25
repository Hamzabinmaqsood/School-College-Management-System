import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, Row } from './academic-tools';
import { AuthService } from './auth';

interface Policy {
  primary_mode: string; late_attended: boolean; excused_policy: string;
  non_teaching_weekdays: number[]; require_rejection_reason: boolean;
}

@Component({
  imports: [FormsModule, RouterLink, MatButtonModule],
  templateUrl: './attendance-settings.html',
})
export class AttendanceSettings {
  readonly api = inject(AdminApi);
  readonly workspace = inject(AcademicWorkspace);
  readonly auth = inject(AuthService);
  readonly state = new RequestState();
  readonly policy = signal<Policy | null>(null);
  readonly holidays = signal<Row[]>([]);
  readonly assignments = signal<Row[]>([]);
  readonly users = signal<Row[]>([]);
  readonly sessions = signal<Row[]>([]);
  readonly classes = signal<Row[]>([]);
  readonly sections = signal<Row[]>([]);
  readonly subjects = signal<Row[]>([]);
  readonly weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  holiday = {id: '', date: '', name: '', kind: 'public'};
  assignment = {user: '', session: '', academic_class: '', section: '', subject: ''};

  constructor() {
    void this.workspace.refresh();
    void this.state.run(async () => {
      const requests: Promise<unknown>[] = [];
      if (this.auth.has('accounts.manage_attendance_settings')) requests.push(
        this.api.read<Policy>('attendance/settings/').then(data => this.policy.set(data)));
      if (this.auth.has('attendance.view_attendanceholiday')) requests.push(this.loadHolidays());
      if (this.auth.has('accounts.manage_teaching_assignments')) {
        requests.push(this.loadAssignments());
        const lookups = [
          ['attendance/assignments/users', this.users], ['academic-sessions', this.sessions],
          ['classes', this.classes], ['sections', this.sections], ['subjects', this.subjects],
        ] as const;
        for (const [path, target] of lookups) requests.push(this.workspace.options(path).then(rows => target.set(rows)));
      }
      await Promise.all(requests);
    });
  }

  can(permission: string) { return this.workspace.can('attendance', permission); }

  toggle(day: number, checked: boolean) {
    this.policy.update(policy => policy && {...policy, non_teaching_weekdays: checked
      ? [...policy.non_teaching_weekdays, day] : policy.non_teaching_weekdays.filter(value => value !== day)});
  }

  savePolicy(policy: Policy) {
    return this.change(async () => this.policy.set(await this.api.write<Policy>('PATCH', 'attendance/settings/', policy)),
      'Attendance policy saved.');
  }

  async loadHolidays() {
    this.holidays.set((await this.api.read<Page<Row>>('attendance/holidays/', {limit: 100})).results);
  }

  async loadAssignments() {
    this.assignments.set((await this.api.read<Page<Row>>('attendance/assignments/', {limit: 100})).results);
  }

  editHoliday(row: Row) {
    this.holiday = {id: row.id, date: String(row['date']), name: String(row['name']), kind: String(row['kind'])};
  }

  saveHoliday() {
    return this.change(async () => {
      const {id, ...data} = this.holiday;
      await this.api.write(id ? 'PATCH' : 'POST', 'attendance/holidays/' + (id ? id + '/' : ''), data);
      this.holiday = {id: '', date: '', name: '', kind: 'public'};
      await this.loadHolidays();
    }, 'Calendar exception saved.');
  }

  assign() {
    return this.change(async () => {
      const data = this.assignment;
      await this.api.write('POST', 'attendance/assignments/', {...data, section: data.section || null,
        subject: data.subject || null});
      await this.loadAssignments();
    }, 'Teaching assignment saved.');
  }

  async toggleAssignment(row: Row) {
    if (!await this.api.confirm(row['active'] ? 'Deactivate this teaching assignment?' : 'Reactivate this teaching assignment?')) return;
    await this.change(async () => {
      await this.api.write('PATCH', 'attendance/assignments/' + row.id + '/', {active: !row['active']});
      await this.loadAssignments();
    }, 'Teaching assignment updated.');
  }

  async change(action: () => Promise<void>, description: string) {
    await this.state.run(action, description);
    void this.workspace.refresh();
  }
}
