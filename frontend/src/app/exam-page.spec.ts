import '@angular/compiler';
import { describe, expect, it } from 'vitest';
import { recordForm } from './academic-tools';
import { examFields, nestedFields } from './exam-config';
import { markUnits } from './exam-page';

describe('examination forms', () => {
  it('keeps blank marks distinct from zero and preserves decimal precision', () => {
    expect(markUnits(null)).toBeNull();
    expect(markUnits('')).toBeNull();
    expect(markUnits('0')).toBe(0n);
    expect(markUnits('80.01')).toBe(8001n);
    expect(markUnits('80.001')).toBeNull();
  });

  it('requires an exam type, session and scheme before creating an examination', () => {
    const form = recordForm(examFields['exams']!);
    form.patchValue({name:'Final', code:'FINAL', start_date:'2026-11-22', end_date:'2026-11-23'});
    expect(form.invalid).toBe(true);
    form.patchValue({session:'term', exam_type:'type', scheme:'scheme'});
    expect(form.valid).toBe(true);
  });

  it('requires the component maximum and name before saving', () => {
    const component = recordForm(nestedFields['subjects']!);
    expect(component.invalid).toBe(true);
    component.patchValue({name:'Practical', maximum:'35.50'});
    expect(component.valid).toBe(true);
  });
});
