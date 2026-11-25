import { Component, input } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Row } from './academic-tools';

export function guardianForm() {
  return new FormGroup({
    guardian: new FormControl('', {nonNullable: true}),
    full_name: new FormControl('', {nonNullable: true}),
    phone: new FormControl('', {nonNullable: true}),
    relationship: new FormControl('', {nonNullable: true, validators: Validators.required}),
    primary: new FormControl(false, {nonNullable: true}),
    emergency: new FormControl(false, {nonNullable: true}),
    pickup: new FormControl(false, {nonNullable: true}),
  });
}

export function guardianPayload(form: ReturnType<typeof guardianForm>) {
  const {guardian, full_name, phone, ...flags} = form.getRawValue();
  if (form.invalid || (!guardian && !(full_name.trim() && phone.trim()))) {
    throw new Error('Choose a guardian or enter a name and phone, and specify the relationship.');
  }
  return {...flags, ...(guardian ? {guardian} : {new_guardian: {full_name, phone}})};
}

@Component({
  selector: 'app-guardian-fields', imports: [ReactiveFormsModule],
  template: '<div class="field-grid" [formGroup]="form()">' +
    '@if (!editing()) { <label>Existing guardian <select formControlName="guardian"><option value="">Select guardian</option>' +
    '@for (row of choices(); track row.id) { <option [value]="row.id">{{ row["full_name"] }} · {{ row["phone"] }}</option> }</select></label>' +
    '@if (!form().controls.guardian.value && canCreate()) { <label>New guardian name <input formControlName="full_name"></label>' +
    '<label>Guardian phone <input formControlName="phone"></label> } }' +
    '<label>Relationship <input formControlName="relationship" required maxlength="64"></label>' +
    '<label class="check-label"><input type="checkbox" formControlName="primary"> Primary guardian</label>' +
    '<label class="check-label"><input type="checkbox" formControlName="emergency"> Emergency contact</label>' +
    '<label class="check-label"><input type="checkbox" formControlName="pickup"> Authorized pickup</label></div>',
})
export class GuardianFormFields {
  readonly form = input.required<ReturnType<typeof guardianForm>>();
  readonly choices = input.required<Row[]>();
  readonly canCreate = input(false);
  readonly editing = input(false);
}
