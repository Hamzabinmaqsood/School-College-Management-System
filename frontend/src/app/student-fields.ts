import { Component, input } from '@angular/core';
import { FormControl, FormRecord, ReactiveFormsModule } from '@angular/forms';
import { Field, Value } from './academic-tools';

export const studentFields: Field[] = [
  {key: 'first_name', label: 'First name', required: true}, {key: 'last_name', label: 'Last name'},
  {key: 'preferred_name', label: 'Preferred name'}, {key: 'admission_number', label: 'Admission number'},
  {key: 'registration_number', label: 'Registration number'},
  {key: 'birth_date', label: 'Date of birth', type: 'date', required: true}, {key: 'gender', label: 'Gender'},
  {key: 'phone', label: 'Contact number'}, {key: 'address', label: 'Address'},
  {key: 'city', label: 'City'}, {key: 'province', label: 'Province'},
  {key: 'admission_date', label: 'Admission date', type: 'date', required: true},
];

@Component({
  selector: 'app-student-fields', imports: [ReactiveFormsModule],
  template: '<div class="field-grid" [formGroup]="form()">' +
    '@for (item of fields; track item.key) { <label>{{ item.label }}' +
    '<input [attr.name]="item.key" [type]="item.type || &quot;text&quot;" [formControlName]="item.key" [required]="item.required || false"></label> }</div>',
})
export class StudentFormFields {
  readonly fields = studentFields;
  readonly form = input.required<FormRecord<FormControl<Value>>>();
}
