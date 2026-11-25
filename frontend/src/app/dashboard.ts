import { Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { StudentMetrics } from './academic-tools';
import { AttendanceSummary } from "./attendance-report";
import { AdminApi } from './admin';
import { licenseLabel, LicenseStatus, licenseTone, renewalMessage } from './license';
import { AuthService } from './auth';
import { Connectivity } from './connectivity';
import { routePermission } from './navigation';

@Component({
  imports: [MatButtonModule, MatIconModule, RouterLink],
  templateUrl: './dashboard.html',
})
export class Dashboard {
  private readonly api = inject(AdminApi);
  readonly subscription = signal<LicenseStatus | null>(null);
  readonly subscriptionLoaded = signal(false);
  readonly subscriptionLabel = licenseLabel;
  readonly subscriptionTone = licenseTone;
  readonly subscriptionReminder = renewalMessage;
  readonly connectivity = inject(Connectivity);
  readonly auth = inject(AuthService);
  readonly studentMetrics = signal<StudentMetrics | null>(null);
  readonly attendance = signal<AttendanceSummary | null>(null);
  readonly timetable = signal<{lessons:{change:string|null}[]} | null>(null);
  readonly attendanceLoaded = signal(false);
  readonly hr = signal<{employees:number;active:number;teachers:number;present?:number;on_leave?:number;pending?:number} | null>(null);
  readonly exams = signal<{active: number; pending: number; awaiting: number; published: number; latest: {exam: string; outcomes: Record<string, number>} | null} | null>(null);
  readonly fees = signal<{collected_this_month: string; outstanding: string; overdue: string; trend: {period: string; amount: string}[]} | null>(null);
  readonly metrics = [
    {label: 'Total Students', icon: 'school', tone: 'blue'},
    {label: 'Total Teachers', icon: 'co_present', tone: 'violet'},
    {label: 'Today’s Attendance', icon: 'fact_check', tone: 'green'},
    {label: 'Monthly Fee Collection', icon: 'payments', tone: 'orange'},
  ];
  readonly actions = computed(() => [
    {label: 'Manage users', path: 'users', icon: 'manage_accounts'},
    {label: 'Manage roles', path: 'roles', icon: 'admin_panel_settings'},
    {label: 'Institution settings', path: 'settings', icon: 'settings'},
    {label: 'Review audit logs', path: 'audit', icon: 'history'},
  ].filter(action => this.auth.has(routePermission(action.path))));

  scheduledLessons() { return this.timetable()?.lessons.filter(row => row.change !== 'cancelled').length ?? 0; }
  substitutions() { return this.timetable()?.lessons.filter(row => row.change === 'substitute').length ?? 0; }

  constructor() {
    void this.connectivity.refresh();
    if (this.auth.has('accounts.view_timetable') || this.auth.has('accounts.view_own_timetable')) {
      void this.api.read<NonNullable<ReturnType<typeof this.timetable>>>('timetables/daily/')
        .then(value => this.timetable.set(value)).catch(() => undefined);
    }
    if (this.auth.has("accounts.view_staff")) {
      void this.api.read<NonNullable<ReturnType<typeof this.hr>>>("hr/overview/").then(data => this.hr.set(data)).catch(() => undefined);
    }
    if (this.auth.has("accounts.view_exam_analytics")) {
      void this.api.read<NonNullable<ReturnType<typeof this.exams>>>("examinations/overview/").then(data => this.exams.set(data)).catch(() => undefined);
    }
    if (this.auth.has("accounts.view_fees")) {
      void this.api.read<NonNullable<ReturnType<typeof this.fees>>>("fees/overview/").then(value => this.fees.set(value)).catch(() => undefined);
    }
    if (this.auth.has("accounts.view_attendance")) {
      void this.api.read<AttendanceSummary>("attendance/summary/").then(data => this.attendance.set(data))
        .catch(() => undefined).finally(() => this.attendanceLoaded.set(true));
    }
    if (this.auth.has('accounts.view_students')) {
      void this.api.read<StudentMetrics>('students/summary/').then(stats => this.studentMetrics.set(stats)).catch(() => undefined);
    }
    void this.api.read<LicenseStatus>('license/status/').then(status => this.subscription.set(status))
      .catch(() => this.subscription.set(null)).finally(() => this.subscriptionLoaded.set(true));
  }
}
