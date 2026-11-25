import '@angular/compiler';
import { describe, expect, it } from 'vitest';
import { recordForm } from './academic-tools';
import { registrationFields } from './fee-config';
import { minorUnits } from './fee-page';

describe('fee forms and exact payment amounts', () => {
  it('uses exact integer minor units for payment entry', () => {
    expect(minorUnits('0.10')).toBe(10n);
    expect(minorUnits('1000.1')).toBe(100010n);
    expect(minorUnits('999999999999.99')).toBe(99999999999999n);
    expect(minorUnits('0.001')).toBeNull();
    expect(minorUnits('-0.01')).toBeNull();
    expect(minorUnits('1e3')).toBeNull();
  });

  it('requires a category name and code', () => {
    const form = recordForm(registrationFields['categories']!);
    expect(form.invalid).toBe(true);
    form.patchValue({name:'Tuition', code:'TUITION'});
    expect(form.valid).toBe(true);
  });

  it('requires a term and month before previewing charges', () => {
    const form = recordForm(registrationFields['billing']!);
    form.patchValue({session:'term'});
    expect(form.invalid).toBe(true);
    form.patchValue({period:'2026-11'});
    expect(form.valid).toBe(true);
  });
});
