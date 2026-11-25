import { Component, input } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Row, sectionsFor } from './academic-tools';

export function placementForm() {
  return new FormGroup({
    session: new FormControl('', {nonNullable: true, validators: Validators.required}),
    academic_class: new FormControl('', {nonNullable: true, validators: Validators.required}),
    section: new FormControl('', {nonNullable: true}),
    roll_number: new FormControl('', {nonNullable: true, validators: [
      Validators.maxLength(32), Validators.pattern(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/),
    ]}),
  });
}

export function placementPayload(form: ReturnType<typeof placementForm>) {
  const value = form.getRawValue();
  return {...value, section: value.section || null};
}

@Component({
  selector: 'app-placement', imports: [ReactiveFormsModule],
  template: '<div class="field-grid" [formGroup]="form()">' +
    '<label>Academic session <select name="session" formControlName="session" required><option value="">Select session</option>' +
    '@for (row of sessions(); track row.id) { <option [value]="row.id">{{ row["name"] }}</option> }</select></label>' +
    '<label>Class <select name="academic_class" formControlName="academic_class" (change)="form().controls.section.reset()" required>' +
    '<option value="">Select class</option>@for (row of classes(); track row.id) { <option [value]="row.id">{{ row["name"] }}</option> }</select></label>' +
    '<label>Section <select name="section" formControlName="section"><option value="">Unassigned</option>' +
    '@for (row of filteredSections(); track row.id) { <option [value]="row.id">{{ row["name"] }}</option> }</select></label>' +
    '<label>Roll number <input name="roll_number" formControlName="roll_number"></label></div>',
})
export class PlacementFields {
  readonly form = input.required<ReturnType<typeof placementForm>>();
  readonly sessions = input.required<Row[]>();
  readonly classes = input.required<Row[]>();
  readonly sections = input.required<Row[]>();
  filteredSections() { return sectionsFor(this.sections(), this.form().controls.academic_class.value); }
}
