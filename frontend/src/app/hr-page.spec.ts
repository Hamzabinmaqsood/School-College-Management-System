import '@angular/compiler';
import { describe, expect, it } from 'vitest';
import { recordForm } from './academic-tools';
import { canExportHrReport, hrForms } from './hr-config';

describe('HR forms', () => {
  it('allows an employee without a login and requires their placement', () => {
    const form = recordForm(hrForms['employees']!);
    form.patchValue({first_name:'Employee',joined_on:'2026-11-22',employment_type:'Contract'});
    expect(form.invalid).toBe(true);
    form.patchValue({department:'science',designation:'teacher'});
    expect(form.valid).toBe(true);
    expect(form.value['user']).toBe('');
  });

  it('requires a payroll period and accepts institution-wide scope', () => {
    const form = recordForm(hrForms['payroll']!);
    expect(form.invalid).toBe(true);
    form.patchValue({period:'november'});
    expect(form.valid).toBe(true);
    expect(form.value['department']).toBe('');
  });

  it('requires amount, date, and payroll entry before posting salary', () => {
    const form = recordForm(hrForms['salary-payments']!);
    form.patchValue({entry:'obligation',amount:'100.01'});
    expect(form.invalid).toBe(true);
    form.patchValue({date:'2026-11-22'});
    expect(form.valid).toBe(true);
  });
});

it('requires payroll export and the report read grant for financial exports', () => {
  const grants = new Set(['accounts.export_hr', 'accounts.view_payroll']);
  const has = (permission: string) => grants.has(permission);
  expect(canExportHrReport('employees', has)).toBe(true);
  expect(canExportHrReport('payroll', has)).toBe(false);
  grants.add('accounts.export_payroll');
  expect(canExportHrReport('payroll', has)).toBe(true);
  expect(canExportHrReport('advances', has)).toBe(false);
  grants.add('accounts.view_salary_setup');
  expect(canExportHrReport('advances', has)).toBe(true);
  grants.delete('accounts.export_hr');
  expect(canExportHrReport('payroll', has)).toBe(false);
});
