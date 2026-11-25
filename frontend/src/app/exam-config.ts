import { Field } from './academic-tools';

const required = (key: string, label: string, type = 'text'): Field => ({key, label, type, required:true});
const pick = (key: string, label: string, lookup: string, mandatory = true): Field =>
  ({key, label, lookup, required: mandatory});
const flag = (key: string, label: string, initial = false): Field => ({key, label, type:'checkbox', initial});
const named = [required('name','Name'), required('code','Code')];
export const examFields: Record<string, Field[]> = {
  types: [...named, {key:'description', label:'Description'}, flag('active','Active',true)],
  exams: [...named, pick('exam_type','Exam type','types'), pick('session','Session','academic-sessions'),
    pick('scheme','Grading scheme','grading-schemes'), required('start_date','Starts','date'),
    required('end_date','Ends','date'),
    {key:'ranking', label:'Positions', options:[['disabled','Disabled'], ['competition','Competition'], ['dense','Dense']], initial:'disabled'},
    flag('rank_by_section','Rank within sections')],
  classes: [pick('exam','Examination','exams'), pick('academic_class','Class','classes')],
  subjects: [pick('group','Exam class','exam-classes'), pick('subject','Subject','subjects'),
    pick('scheme','Alternate scheme','grading-schemes',false), flag('optional','Optional subject'),
    flag('weighted','Weighted assessment'), {key:'passing_percentage', label:'Passing percentage', initial:'0'}],
  schedules: [pick('subject','Exam subject','exam-subjects'), required('date','Date','date'),
    required('start_time','Start','time'), required('end_time','End','time'),
    {key:'room', label:'Room'}, {key:'instructions', label:'Instructions'}],
  'grading-schemes': [required('name','Scheme name'), required('effective_from','Effective from','date'),
    required('effective_to','Effective through','date'),
    {key:'basis',label:'Grade basis',options:[['percentage','Percentage'],['marks','Obtained marks']],initial:'percentage'}],
  registrations: [pick('group','Exam class','exam-classes'), pick('enrollment','Student enrollment','enrollments'),
    {key:'optional_subjects',label:'Optional subjects',type:'optional-subjects'}, flag('excluded','Exclude from roster'),
    required('reason','Reason')],
  results: [pick('group','Exam class','exam-classes')],
};
export const nestedFields: Record<string, Field[]> = {
  'grading-schemes': [required('label','Grade'), required('minimum','Lower boundary'),
    {key:'points', label:'Grade points'}, flag('passing','Passing',true)],
  subjects: [required('name','Component name'), required('maximum','Maximum marks'),
    {key:'minimum',label:'Minimum passing marks'}, {key:'weight',label:'Weight percent'}, flag('required','Required',true)],
};
const view = 'accounts.view_examinations';
const manage = 'accounts.manage_examinations';
export const examPages: Record<string, [string, string, string?]> = {
  overview:['Examinations',view], types:['Exam types',view,manage], create:['Examination configuration',view,manage],
  classes:['Participating classes',view,'accounts.configure_exam_assessments'],
  schedules:['Exam schedules',view,'accounts.manage_exam_schedule'],
  subjects:['Subjects and assessments',view,'accounts.configure_exam_assessments'],
  marks:['Marks entry','accounts.view_exam_marks'], review:['Marks review','accounts.view_exam_marks'],
  results:['Result processing','accounts.view_class_results','accounts.approve_exam_results'],
  grading:['Grading schemes',view,'accounts.manage_exam_grading'],
  reports:['Examination reports','accounts.view_class_results'],
  settings:['Roster exceptions','accounts.configure_exam_assessments','accounts.configure_exam_assessments'],
};
