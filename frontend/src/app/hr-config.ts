import { Field } from './academic-tools';

const field = (key: string, label: string, type = 'text', required = true): Field => ({key,label,type,required});
const pick = (key: string, label: string, lookup: string, required = true): Field => ({key,label,lookup,required});
const flag = (key: string, label: string, initial = false): Field => ({key,label,type:'checkbox',initial});
const choices = (key: string, label: string, options: string[], initial = options[0]): Field =>
  ({key,label,options:options.map(value => [value,value.replaceAll('_',' ')]),initial});
const named = [field('name','Name'),field('code','Code')];
const person = pick('employee','Employee','employees');
const dates = [field('start_date','Effective from','date'),field('end_date','Effective through','date')];
export const hrForms: Record<string,Field[]> = {
  settings:[field("employee_prefix","Employee prefix"),field("next_employee_number","Next employee number","number"),
    field("document_retention_days","Default document retention days","number",false),
    field("document_retention_by_kind","Retention days by document type (JSON)","text",false),
    flag('separate_salary_structure_approver','Require a separate salary structure approver',true)],
  "payroll-adjustments":[field("entry","Payroll entry ID"),field("amount","Signed adjustment amount"),field("reason","Reason")],
  departments:[...named,field('description','Description','text',false),field('default_schedule','Default schedule (JSON)','text',false),flag('active','Active',true)],
  designations:[...named,flag('teaching','Teaching role'),flag('active','Active',true)],
  employees:[field('code','Employee code (optional)','text',false),field('first_name','First name'),field('last_name','Last name','text',false),
    field('display_name','Display name','text',false),pick('department','Department','departments'),
    pick('designation','Designation','designations'),field('user','Existing account ID','text',false),
    field('employment_type','Employment type'),field('joined_on','Joined on','date'),
    field('ended_on','Exit date','date',false),choices('status','Status',['active','on_leave','suspended','resigned','terminated','retired','contract_ended'])],
  contracts:[person,field('kind','Contract type'),...dates,field('weekdays','Working days (0–6, comma-separated)','text',false),
    field('shift_start','Shift start','time',false),field('shift_end','Shift end','time',false),
    field('break_minutes','Break (minutes)','number',false),
    field('late_tolerance_minutes','Late tolerance (minutes)','number',false),
    field('early_tolerance_minutes','Early tolerance (minutes)','number',false),
    flag('use_department_schedule','Copy the department schedule'),
    field('leave_entitlements','Annual leave overrides by leave code (JSON)','text',false),flag('active','Active',true)],
  attendance:[person,field('date','Date','date'),choices('status','Status',['present','absent','late','leave','holiday','excused']),
    field('check_in','Check in','time',false),field('check_out','Check out','time',false),field('remarks','Remarks','text',false)],
  'leave-types':[...named,field('annual_days','Annual days','number'),
    choices('accrual_mode','Leave policy',['legacy','monthly','annual','fixed','manual','none']),
    field('accrual_start','Accrual begins','date',false),flag('prorate','Prorate entitlement',true),
    field('carry_limit','Maximum days to carry','number',false),
    field('carry_expiry_days','Carry expiry days from January 1','number',false),
    field('maximum_balance','Maximum accrued balance','number',false),flag('allow_negative','Allow negative balance'),flag('paid','Paid leave',true),flag('active','Active',true)],
  leaves:[person,pick('leave_type','Leave type','leave-types'),...dates,field('reason','Reason')],
  'salary-structures':[...named,choices('basis','Basis',['monthly','daily','hourly','contract']),
    field('basic','Basic amount'),field('unpaid_leave_daily_rate','Unpaid leave daily deduction','number',false),flag('prorate','Prorate monthly base'),
    field('effective_from','Effective from','date',false),field('effective_through','Effective through','date',false)],
  'salary-assignments':[person,pick('structure','Salary structure','salary-structures'),...dates],
  advances:[person,field('amount','Advance amount'),field('installment','Recovery installment'),field('recover_from','Recover from','date')],
  'overtime-policies':[field('name','Policy name'),...dates,field('rate','Fixed hourly rate (0 for salary derived)'),
    field('monthly_divisor','Hours per month for salary-derived rate','number',false),
    field('regular_multiplier','Regular day multiplier'),field('rest_multiplier','Rest day multiplier'),
    field('holiday_multiplier','Holiday multiplier'),field('minimum_hours','Minimum hours'),
    field('maximum_hours','Maximum hours'),flag('separate_approver','Require a separate reviewer',true)],
  overtime:[field('attendance','Attendance record ID'),pick('policy','Overtime policy','overtime-policies'),
    field('requested_hours','Requested hours')],
  periods:[field('name','Period name'),...dates,flag('separate_approver','Require a separate approver',true)],
  payroll:[pick('period','Payroll period','periods'),pick('department','Department','departments',false)],
  'salary-payments':[field('entry','Payroll entry ID'),field('amount','Amount'),field('date','Payment date','date'),
    choices('method','Payment method',['cash','bank_transfer','cheque','digital_transfer','other']),
    field('external_reference','External reference','text',false)],
};
export const salaryLine = [field('label','Component'),choices('kind','Type',['earning','deduction']),field('amount','Amount')];
export const hrPages: Record<string,[string,string,string?]> = {
  settings:['HR settings','accounts.manage_hr_registry','accounts.manage_hr_registry'],
  "payroll-adjustments":['Payroll adjustments','accounts.view_payroll','accounts.correct_payroll'],
  overview:['Human resources','accounts.view_staff'],
  employees:['Employees','accounts.view_staff','accounts.add_employee'],
  departments:['Departments','accounts.view_staff','accounts.manage_hr_registry'],
  designations:['Designations','accounts.view_staff','accounts.manage_hr_registry'],
  teachers:['Teachers','accounts.view_teachers'],
  contracts:['Employment contracts','accounts.view_staff','accounts.manage_hr_registry'],
  attendance:['Staff attendance','accounts.view_staff_attendance','accounts.mark_staff_attendance'],
  'leave-types':['Leave types','accounts.view_staff_leave','accounts.manage_hr_registry'],
  leaves:['Employee leave','accounts.view_staff_leave','accounts.request_staff_leave'],
  'salary-structures':['Salary structures','accounts.view_salary_setup','accounts.manage_salary_setup'],
  'salary-assignments':['Salary assignments','accounts.view_salary_setup','accounts.manage_salary_setup'],
  advances:['Salary advances','accounts.view_salary_setup','accounts.manage_salary_setup'],
  periods:['Payroll periods','accounts.view_payroll','accounts.generate_payroll'],
  'overtime-policies':['Overtime policies','accounts.view_payroll','accounts.generate_payroll'],
  overtime:['Overtime requests','accounts.view_payroll','accounts.generate_payroll'],
  'documents/due':['Retention review queue','accounts.manage_employee_documents'],
  payslips:["Payslips","accounts.view_payroll"],
  payroll:['Payroll','accounts.view_payroll','accounts.generate_payroll'],
  'salary-payments':['Salary payments','accounts.view_payroll','accounts.pay_salary'],
  reports:['HR reports','accounts.view_staff'],
};

const payrollExportGrants: Record<string, string> = {
  payroll: 'accounts.view_payroll',
  'outstanding-payables': 'accounts.view_payroll',
  'salary-payments': 'accounts.view_payroll',
  adjustments: 'accounts.view_payroll',
  'salary-structures': 'accounts.view_salary_setup',
  advances: 'accounts.view_salary_setup',
};

export function canExportHrReport(report: string, has: (permission: string) => boolean): boolean {
  const readGrant = payrollExportGrants[report];
  return has('accounts.export_hr') &&
    (!readGrant || (has('accounts.export_payroll') && has(readGrant)));
}
