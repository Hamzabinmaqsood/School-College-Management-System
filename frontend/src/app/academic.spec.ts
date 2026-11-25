import '@angular/compiler';
import { describe, expect, it } from 'vitest';
import { registries } from './academic-config';
import { csvLink, permitWrite, recordForm, sectionsFor, validateDateRange } from './academic-tools';
import { destination, errorMessage } from './auth';
import { HttpErrorResponse } from '@angular/common/http';
import { guardianForm, guardianPayload } from './guardian-fields';
import { placementForm, placementPayload } from './placement';
import { studentFields } from './student-fields';

describe('academic and student forms', () => {
  it('validates academic session date ranges', () => {
    const form = recordForm(registries['sessions']!.fields);
    form.addValidators(validateDateRange);
    form.patchValue({name:'Term A', code:'A', start_date:'2026-06-01', end_date:'2026-05-01'});
    expect(form.hasError('dateRange')).toBe(true);
    form.patchValue({end_date:'2026-12-01'});
    expect(form.valid).toBe(true);
  });

  it('requires class selection for sections and subjects for assignments', () => {
    const section = recordForm(registries['sections']!.fields);
    section.patchValue({name: 'Blue', code: 'BLUE'});
    expect(section.invalid).toBe(true);
    section.patchValue({academic_class: 'class-one'});
    expect(section.valid).toBe(true);
    const assignment = recordForm(registries['class-subjects']!.fields);
    assignment.patchValue({academic_class: 'class-one', subject: 'math'});
    expect(assignment.valid).toBe(true);
    expect(assignment.value['mandatory']).toBe(true);
  });

  it('filters section choices and serializes optional placement', () => {
    const sections = [{id:'a', academic_class:'class-one', active:true},
      {id:'b', academic_class:'class-two', active:true}, {id:'c', academic_class:'class-one', active:false}];
    expect(sectionsFor(sections, 'class-one').map(row => row.id)).toEqual(['a']);
    const form = placementForm();
    form.patchValue({session:'one', academic_class:'class-one'});
    expect(placementPayload(form).section).toBeNull();
    form.patchValue({roll_number:'invalid roll'});
    expect(form.invalid).toBe(true);
  });

  it('keeps optional admission numbers and validates minimum student information', () => {
    const form = recordForm(studentFields);
    expect(form.invalid).toBe(true);
    form.patchValue({first_name: 'طالب علم', birth_date:'2012-03-01', admission_date:'2026-11-01'});
    expect(form.valid).toBe(true);
    expect(form.getRawValue()['admission_number']).toBe('');
  });

  it('supports linking or entering a guardian with relationship flags', () => {
    const form = guardianForm();
    expect(() => guardianPayload(form)).toThrow('guardian');
    form.patchValue({guardian:'guardian-id', relationship:'Parent', primary:true});
    expect(guardianPayload(form)).toMatchObject({guardian:'guardian-id', relationship:'Parent', primary:true});
    form.patchValue({guardian:'', full_name:'Guardian', phone:'555-0101'});
    expect(guardianPayload(form)).toMatchObject({new_guardian:{full_name:'Guardian', phone:'555-0101'}});
  });

  it('keeps Unicode and cohort filters in export URLs and shows nested errors', () => {
    const url = new URL(csvLink('students/export/', {search:'علی', session:'s-1', section:''}), 'http://localhost');
    expect(url.searchParams.get('search')).toBe('علی');
    expect(url.searchParams.get('session')).toBe('s-1');
    expect(url.searchParams.has('section')).toBe(false);
    expect(errorMessage(new HttpErrorResponse({status:400,error:{details:{student:{birth_date:['Invalid date.']}}}})))
      .toBe('Invalid date.');
  });

  it('keeps expired screens readable while requiring both grants and features for admissions', () => {
    const grant = 'admissions.add_studentenrollment';
    const active = {status:'ACTIVE', write_allowed:true, available_features:['admissions', 'students']};
    expect(permitWrite(active, ['students','admissions'], [grant], grant)).toBe(true);
    expect(permitWrite(active, ['students','academics'], [grant], grant)).toBe(false);
    expect(permitWrite(active, ['students','admissions'], [], grant)).toBe(false);
    expect(permitWrite({...active, status:'EXPIRED', write_allowed:false}, ['students'], [grant], grant)).toBe(false);
    const timetableGrant = 'accounts.manage_timetable';
    expect(permitWrite(active, ['timetables'], [timetableGrant], timetableGrant)).toBe(false);
    const entitled = {...active, available_features:['timetables']};
    expect(permitWrite(entitled, ['timetables'], [timetableGrant], timetableGrant)).toBe(true);
    expect(permitWrite(entitled, ['timetables'], ['accounts.view_own_timetable'], timetableGrant)).toBe(false);
    expect(destination(null, '/students/example')).toBe('/login');
  });
});
