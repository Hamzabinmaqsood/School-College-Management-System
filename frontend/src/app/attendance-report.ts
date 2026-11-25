import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AuthService } from './auth';
import { attendanceMonth } from "./attendance-calendar";
import { Value } from './academic-tools';

type DataRow = Record<string, Value>;
export interface AttendanceTotals {
  eligible: number; draft: number; present: number; absent: number;
  late: number; excused: number; unmarked: number; percentage: number | null;
}
export interface AttendanceSummary {
  date: string; mode: string; status: string; expected: number; totals: AttendanceTotals;
  trend: (AttendanceTotals & {date: string})[];
  classes: DataRow[];
}
interface StudentAttendance {
  totals: AttendanceTotals; calendar: (AttendanceTotals & {date: string})[];
  subjects: DataRow[]; records: Page<DataRow>; approved_leaves: DataRow[] | null;
}
interface ReportFilters {
  sessions: DataRow[]; classes: DataRow[]; sections: DataRow[]; subjects: DataRow[];
  students: DataRow[]; primary_mode: string;
}

@Component({
  selector: 'app-attendance-report',
  imports: [FormsModule, RouterLink, MatButtonModule],
  templateUrl: './attendance-report.html',
})
export class AttendanceReport implements OnInit {
  @Input() studentId = '';
  readonly api = inject(AdminApi);
  readonly auth = inject(AuthService);
  readonly state = new RequestState();
  readonly page = signal<Page<DataRow> | null>(null);
  readonly student = signal<StudentAttendance | null>(null);
  readonly columns = signal<string[]>([]);
  readonly choices = signal<ReportFilters | null>(null);
  filters = {from_date: '', to_date: '', mode: 'daily', report: 'class', threshold: 75,
    session: '', academic_class: '', section: '', subject: '', student: ''};
  readonly reports = [
    ['class', 'Class and section'], ['daily', 'Register detail'], ['monthly', 'Monthly'],
    ['student', 'Per student'], ['subject', 'Subject frequency'], ['percentage', 'Attendance percentage'],
    ['low', 'Low attendance'], ['leave', 'Leave summary'],
  ];
  params: Record<string, string> = {};
  offset = 0;
  month = '';

  showMonth() {
    const dates = attendanceMonth(this.month);
    if (!dates) return;
    this.filters = {...this.filters, ...dates};
    return this.apply();
  }
  readonly limit = 30;

  ngOnInit() { void this.prepare(); }

  async prepare() {
    await this.state.run(async () => {
      const criteria: Record<string, string> = this.studentId ? {student: this.studentId} : {};
      const data = await this.api.read<ReportFilters>('attendance/report-filters/', criteria);
      this.choices.set(data);
      this.filters.mode = data.primary_mode;
    });
    if (!this.state.error()) await this.apply();
  }

  apply() {
    const fields = this.studentId
      ? {from_date: this.filters.from_date, to_date: this.filters.to_date, mode: this.filters.mode, session: this.filters.session}
      : this.filters;
    this.params = Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== '')
      .map(([key, value]) => [key, String(value)]));
    return this.load(0);
  }

  async load(offset: number) {
    await this.state.run(async () => {
      const params = {...this.params, limit: this.limit, offset};
      let data: Page<DataRow>;
      if (this.studentId) {
        const result = await this.api.read<StudentAttendance>('attendance/student/' + this.studentId + '/', params);
        this.student.set(result);
        data = result.records;
      } else {
        data = await this.api.read<Page<DataRow>>('attendance/reports/', params);
      }
      this.offset = offset;
      this.page.set(data);
      this.columns.set(Object.keys(data.results[0] ?? {}));
    });
  }

  link(output: string) {
    return '/api/v1/attendance/' + output + '/?' + new URLSearchParams(this.params).toString();
  }

  title(column: string) {
    return column.replace(/^(register|student)__/, '').replaceAll('_', ' ');
  }
}
