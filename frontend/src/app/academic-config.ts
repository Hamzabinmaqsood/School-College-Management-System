import { Field } from './academic-tools';

export interface Registry {
  title: string;
  resource: string;
  add: string;
  change: string;
  feature: string;
  fields: Field[];
  columns: [string, string][];
  filter?: Field;
}

const named: Field[] = [{key: 'name', label: 'Name', required: true}, {key: 'code', label: 'Code', required: true}];
const active: Field = {key: 'active', label: 'Active', type: 'checkbox', initial: true};
const statuses: [string, string][] = [['planned', 'Planned'], ['active', 'Active'], ['closed', 'Closed']];
const activeFilter: Field = {key: 'active', label: 'Status', options: [['true', 'Active'], ['false', 'Inactive']]};
const registry = (title: string, resource: string, model: string, fields: Field[], columns: [string, string][],
  filter = activeFilter, app = 'academics'): Registry => ({
  title, resource, add: app + '.add_' + model, change: app + '.change_' + model,
  feature: app === 'students' ? 'students' : 'academics', fields, columns, filter,
});

export const registries: Record<string, Registry> = {
  sessions: registry('Academic sessions', 'academic-sessions', 'academicsession', [...named,
    {key: 'start_date', label: 'Start date', type: 'date', required: true},
    {key: 'end_date', label: 'End date', type: 'date', required: true},
    {key: 'status', label: 'Status', options: statuses, initial: 'planned'},
  ], [['name', 'Session'], ['code', 'Code'], ['start_date', 'Starts'], ['end_date', 'Ends'], ['status', 'Status'],
    ['is_current', 'Current']], {key: 'status', label: 'Status', options: statuses}),
  classes: registry('Classes', 'classes', 'academicclass', [...named, {key: 'category', label: 'Category'},
    {key: 'display_order', label: 'Display order', type: 'number', initial: 0}, active],
  [['name', 'Class'], ['code', 'Code'], ['category', 'Category'], ['display_order', 'Order'], ['active', 'Status']]),
  sections: registry('Sections', 'sections', 'section', [...named,
    {key: 'academic_class', label: 'Class', lookup: 'classes', required: true, immutable: true},
    {key: 'capacity', label: 'Capacity', type: 'number', initial: null}, active],
  [['name', 'Section'], ['code', 'Code'], ['class_name', 'Class'], ['capacity', 'Capacity'], ['active', 'Status']]),
  subjects: registry('Subjects', 'subjects', 'subject', [...named, {key: 'description', label: 'Description'}, active],
  [['name', 'Subject'], ['code', 'Code'], ['description', 'Description'], ['active', 'Status']]),
  'class-subjects': registry('Class subject assignments', 'class-subjects', 'classsubject', [
    {key: 'academic_class', label: 'Class', lookup: 'classes', required: true, immutable: true},
    {key: 'subject', label: 'Subject', lookup: 'subjects', required: true, immutable: true},
    {key: 'session', label: 'Session', lookup: 'academic-sessions', immutable: true},
    {key: 'mandatory', label: 'Mandatory subject', type: 'checkbox', initial: true}, active,
  ], [['class_name', 'Class'], ['subject_name', 'Subject'], ['session_name', 'Session'], ['mandatory', 'Mandatory'], ['active', 'Status']]),
  guardians: registry('Guardians', 'guardians', 'guardian', [
    {key: 'full_name', label: 'Full name', required: true}, {key: 'phone', label: 'Contact number', required: true},
    {key: 'alternate_phone', label: 'Alternative contact'}, {key: 'email', label: 'Email', type: 'email'},
    {key: 'address', label: 'Address'}, {key: 'occupation', label: 'Occupation'},
  ], [['full_name', 'Guardian'], ['phone', 'Contact number'], ['email', 'Email']], {key: '', label: ''}, 'students'),
};
