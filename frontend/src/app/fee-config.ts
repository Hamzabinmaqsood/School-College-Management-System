import { Field } from './academic-tools';

const recurrence: [string, string][] = [
  ['monthly', 'Monthly'], ['quarterly', 'Quarterly'], ['term', 'Academic term'],
  ['annual', 'Annual'], ['one_time', 'One-time'], ['custom', 'Custom'],
];
const name: Field = {key:'name', label:'Name', required:true};
const session: Field = {key:'session', label:'Academic session', lookup:'sessions', required:true};
const academicClass: Field = {key:'academic_class', label:'Class', lookup:'classes'};
const section: Field = {key:'section', label:'Section', lookup:'sections'};
const student: Field = {key:'student', label:'Student', lookup:'students'};
const category: Field = {key:'category', label:'Fee category', lookup:'categories'};
const dates: Field[] = [
  {key:'start_date', label:'Effective from', type:'date', required:true},
  {key:'end_date', label:'Effective through', type:'date', required:true},
];
const active: Field = {key:'active', label:'Active', type:'checkbox', initial:true};
const amount: Field = {key:'amount', label:'Amount', type:'text'};
const reason: Field = {key:'reason', label:'Reason', required:true};
export const lineFields: Field[] = [{...category, required:true}, {...amount, required:true},
  {key:'recurrence', label:'Recurrence', options:recurrence, initial:'monthly'}];
export const registrationFields: Record<string, Field[]> = {
  categories: [name, {key:'code', label:'Code', required:true}, {key:'description', label:'Description'},
    lineFields[2]!, active],
  structures: [name, session, {...academicClass, required:true}, section, ...dates],
  assignments: [{key:'enrollment', label:'Enrollment', lookup:'enrollments', required:true},
    {key:'structure', label:'Alternate structure', lookup:'structures'}, category, amount, ...dates, active],
  concessions: [{...student, required:true}, session, category, {key:'label', label:'Concession name', required:true},
    {key:'kind', label:'Calculation', options:[['fixed','Fixed amount'], ['percent','Percentage'], ['full','Full scholarship']], initial:'fixed'},
    {key:'value', label:'Amount or percentage', initial:'0.00'}, ...dates],
  billing: [session, {key:'period', label:'Billing month', type:'month', required:true},
    academicClass, section, student, {key:'structure', label:'Structure', lookup:'structures'},
    {key:'reference', label:'One-time or custom reference'}],
  adjustments: [{key:'invoice', label:'Invoice', lookup:'invoices', required:true},
    {key:'kind', label:'Adjustment type', options:[['debit','Debit'],['credit','Credit'],['write_off','Write-off']], initial:'credit'},
    {...amount, required:true}, reason],
  refunds: [{key:'allocation', label:'Payment allocation ID', required:true},
    {key:'date', label:'Refund date', type:'date', required:true}, {...amount, required:true}, reason],
  settings: [
    {key:'currency', label:'Currency', options:[['PKR','PKR']], initial:'PKR'},
    {key:'invoice_prefix', label:'Invoice prefix', required:true},
    {key:'receipt_prefix', label:'Receipt prefix', required:true},
    {key:'billing_day', label:'Billing day', type:'number'}, {key:'due_day', label:'Due day', type:'number'},
    {key:'grace_days', label:'Late-fee grace days', type:'number'}, {key:'late_fee', label:'Late fee amount'},
    {key:'payment_methods', label:'Payment method codes, comma-separated'},
    {key:'late_fee_enabled', label:'Enable late fee settings', type:'checkbox'},
    {key:'stack_discounts', label:'Stack concessions', type:'checkbox'},
    {key:'prorate', label:'Prorate monthly charges', type:'checkbox'},
    {key:'dual_approval', label:'Require separate adjustment approver', type:'checkbox'},
    {key:'receipt_footer', label:'Receipt footer'}, {key:'challan_instructions', label:'Challan instructions'},
  ],
};
export const feePages: Record<string, [string, string, string?]> = {
  overview:['Fee management','accounts.view_fees'],
  categories:['Fee categories','fees.view_feecategory','fees.change_feecategory'],
  structures:['Fee structures','fees.view_feestructure','fees.change_feestructure'],
  assignments:['Student fee assignments','fees.view_studentfeeassignment','fees.change_studentfeeassignment'],
  concessions:['Discounts and scholarships','fees.view_studentconcession','fees.change_studentconcession'],
  billing:['Monthly billing','accounts.generate_fee_invoices','accounts.generate_fee_invoices'],
  invoices:['Invoices','fees.view_feeinvoice'],
  collect:['Collect a payment','accounts.collect_fees','accounts.collect_fees'],
  payments:['Payment history','fees.view_feepayment'],
  adjustments:['Invoice adjustments','fees.view_feeadjustment','accounts.manage_fee_adjustments'],
  refunds:['Refunds','fees.view_feerefund','accounts.approve_fee_refund'],
  outstanding:['Outstanding fees','accounts.view_fee_reports'],
  reports:['Financial reports','accounts.view_fee_reports'],
  settings:['Fee settings','accounts.manage_fee_settings','accounts.manage_fee_settings'],
};
