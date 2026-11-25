import { TimetablePage } from './timetable-page';
import { AcademicPage } from './academic-page';
import { FeePage } from "./fee-page";
import { HrPage } from "./hr-page";
import { hrPages } from "./hr-config";
import { ExamPage } from "./exam-page";
import { examPages } from "./exam-config";
import { feePages } from "./fee-config";
import { AttendancePage } from "./attendance-page";
import { AttendanceReport } from "./attendance-report";
import { AttendanceLeaves } from "./attendance-leaves";
import { AttendanceSettings } from "./attendance-settings";
import { registries } from './academic-config';
import { AdmissionWizard } from './admission-wizard';
import { StudentList } from './student-list';
import { StudentProfile } from './student-profile';
import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink, Routes } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AppShell } from './app';
import { accountGuard } from './auth';
import { AuthPage } from './auth-page';
import { AuditPage } from './audit-page';
import { Dashboard } from './dashboard';
import { LicensePage } from './license-page';
import { InstitutionPage } from './institution-page';
import { navigation, routePermission } from './navigation';
import { RolesPage } from './roles-page';
import { UsersPage } from './users-page';

@Component({
  imports: [MatIconModule, RouterLink],
  template: '<h1>{{ title }}</h1><section class="panel empty-page"><mat-icon>folder_open</mat-icon>' +
    '<p>{{ title === "Access denied" ? "Your current role does not allow access to this page." : "This module is planned for a later phase." }}</p>' +
    '@if (title !== "Access denied") { <a routerLink="/dashboard">Back to dashboard</a> }</section>',
})
export class ModulePlaceholder {
  readonly title = inject(ActivatedRoute).snapshot.title;
}

const managed = new Set(['dashboard', 'users', 'roles', 'settings', 'audit', 'subscription', 'students', 'admissions', 'attendance', 'fees', 'examinations', 'staff', 'teachers', 'payroll', ...Object.keys(registries)]);

export const routes: Routes = [
  {path: 'login', title: 'Sign in', component: AuthPage, canActivate: [accountGuard]},
  {path: 'change-password', title: 'Change password', component: AuthPage, data: {change: true}, canActivate: [accountGuard]},
  {path: 'setup/institution', title: 'Institution setup', component: InstitutionPage,
    data: {setup: true, permission: 'accounts.change_institution'}, canActivate: [accountGuard]},
  {path: '', component: AppShell, canActivateChild: [accountGuard], children: [
    {path: '', pathMatch: 'full', redirectTo: 'dashboard'},
    {path: "attendance/reports", title: "Attendance reports", component: AttendanceReport,
      data: {permission: "accounts.view_attendance_history"}},
    {path: "attendance/leaves", title: "Student leave", component: AttendanceLeaves,
      data: {permission: "attendance.view_studentleaverequest"}},
    {path: "attendance/settings", title: "Attendance settings", component: AttendanceSettings,
      data: {anyPermission: ["accounts.manage_attendance_settings", "attendance.view_attendanceholiday", "accounts.manage_teaching_assignments"]}},
    {path:"timetable", component:TimetablePage, title:"Timetable",
      data:{anyPermission:["accounts.view_timetable","accounts.view_own_timetable"]}},
    {path: "attendance/history", title: "Attendance history", component: AttendancePage,
      data: {history: true, permission: "accounts.view_attendance_history"}},
    {path: "attendance", title: "Attendance", component: AttendancePage,
      data: {permission: "attendance.view_attendancesession"}, canDeactivate: [(page: AttendancePage) => page.leave()]},
    {path:"staff", redirectTo:"hr/employees", pathMatch:"full"},
    {path:"teachers", redirectTo:"hr/teachers", pathMatch:"full"},
    {path:"payroll", redirectTo:"hr/payroll", pathMatch:"full"},
    {path:"hr/employees/new", component:HrPage, title:"New employee", data:{hrPage:"employees",permission:"accounts.add_employee"}},
    {path:"hr/employees/:id", component:HrPage, title:"Employee profile", data:{hrPage:"employees",permission:"accounts.view_staff"}},
    {path:"hr/attendance/calendar", redirectTo:"hr/attendance", pathMatch:"full"},
    {path:"hr/payroll/generate", redirectTo:"hr/payroll", pathMatch:"full"},
    {path:"hr/payroll/:id", component:HrPage, title:"Payroll details", data:{hrPage:"payroll",permission:"accounts.view_payroll"}},
    ...Object.entries(hrPages).map(([name, config]) => ({
      path: name === "overview" ? "hr" : "hr/" + name, title: config[0], component: HrPage,
      data: {hrPage: name, permission: config[1]}, canDeactivate: [(page: HrPage) => page.leave()],
    })),
    ...Object.entries(examPages).map(([name, config]) => ({
      path: name === "overview" ? "examinations" : "examinations/" + name, title: config[0], component: ExamPage,
      data: {examPage: name, permission: config[1]}, canDeactivate: [(page: ExamPage) => page.leave()],
    })),
    ...Object.entries(feePages).map(([name, config]) => ({
      path: name === "overview" ? "fees" : "fees/" + name, title: config[0], component: FeePage,
      data: {feePage: name, permission: config[1]},
    })),
    ...Object.entries(registries).map(([path, registry]) => ({
      path, title: registry.title, component: AcademicPage, data: {registry: path, permission: routePermission(path)},
    })),
    {path: 'admissions/new', title: 'New admission', component: AdmissionWizard, data: {permission: 'admissions.add_studentenrollment'}},
    {path: 'admissions', title: 'Admissions', component: StudentList, data: {admissions: true, permission: routePermission('admissions')}},
    {path: 'students', title: 'Students', component: StudentList, data: {permission: routePermission('students')}},
    {path: 'students/:id/print', title: 'Print student profile', component: StudentProfile,
      data: {print: true, permission: 'accounts.print_students'}},
    {path: 'students/:id', title: 'Student profile', component: StudentProfile, data: {permission: 'accounts.view_student_details'}},
    {path: 'dashboard', title: 'Dashboard', component: Dashboard, data: {permission: routePermission('dashboard')}},
    {path: 'users', title: 'User management', component: UsersPage, data: {permission: routePermission('users')}},
    {path: 'roles', title: 'Role management', component: RolesPage, data: {permission: routePermission('roles')},
      canDeactivate: [(page: RolesPage) => page.leaveMatrix()]},
    {path: 'settings', title: 'Institution settings', component: InstitutionPage, data: {permission: routePermission('settings')}},
    {path: 'audit', title: 'Audit logs', component: AuditPage, data: {permission: routePermission('audit')}},
    {path: 'subscription', title: 'Subscription', component: LicensePage, data: {permission: routePermission('subscription')}},
    {path: 'activation', title: 'Activate license', component: LicensePage,
      data: {permission: 'accounts.manage_subscription', activation: true}},
    {path: 'access-denied', title: 'Access denied', component: ModulePlaceholder},
    ...navigation.flatMap(group => group.items).filter(item => !managed.has(item.path)).map(item => ({
      path: item.path, component: ModulePlaceholder, title: item.label, data: {permission: routePermission(item.path)},
    })),
    {path: '**', redirectTo: 'dashboard'},
  ]},
];
