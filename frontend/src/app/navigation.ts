const group = (title: string, items: [string, string, string][]) => ({
  title, items: items.map(([label, path, icon]) => ({label, path, icon})),
});
export const navigation = [
  group('Overview', [['Dashboard', 'dashboard', 'space_dashboard']]),
  group('Academic Management', [
    ['Students', 'students', 'school'], ['Admissions', 'admissions', 'person_add'],
    ['Classes', 'classes', 'view_module'], ['Sections', 'sections', 'view_list'], ['Subjects', 'subjects', 'menu_book'],
    ['Academic Sessions', 'sessions', 'event'], ['Class Subject Assignments', 'class-subjects', 'assignment'], ['Guardians', 'guardians', 'family_restroom'], ['Attendance', 'attendance', 'fact_check'],
    ['Examinations', 'examinations', 'assignment'], ['Timetable', 'timetable', 'calendar_month'],
  ]),
  group('Human Resources', [
    ['Teachers', 'teachers', 'co_present'], ['Staff', 'staff', 'badge'], ['Payroll', 'payroll', 'payments'],
  ]),
  group('Finance', [
    ['Fee Management', 'fees', 'receipt_long'], ['Income', 'income', 'south_west'],
    ['Expenses', 'expenses', 'north_east'], ['Accounts', 'accounts', 'account_balance'],
  ]),
  group('Services', [['Library', 'library', 'local_library'], ['Transport', 'transport', 'directions_bus']]),
  group('Administration', [
    ['Reports', 'reports', 'analytics'], ["Users", "users", "manage_accounts"], ["Roles", "roles", "admin_panel_settings"],
    ['Audit Logs', 'audit', 'history'], ['Subscription', 'subscription', 'card_membership'],
    ['Settings', 'settings', 'settings'],
  ]),
];

const permissions: Record<string, string> = {
  users: 'accounts.view_user',
  roles: 'auth.view_group',
  settings: 'accounts.view_institution',
  audit: 'audit.view_auditevent',
  guardians: 'students.view_guardian',
  'class-subjects': 'academics.view_classsubject',
};

export function routePermission(path: string) {
  return permissions[path] ?? 'accounts.view_' + path;
}

export function visibleNavigation(grants: string[]) {
  return navigation
    .map(group => ({...group, items: group.items.filter(item => grants.includes(routePermission(item.path)) || (item.path === 'timetable' && grants.includes('accounts.view_own_timetable')) || (item.path === 'subscription' && grants.includes('accounts.manage_subscription')))}))
    .filter(group => group.items.length);
}
