import { Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { Router, RouterLink } from '@angular/router';
import { AdminApi, RequestState } from './admin';
import { AcademicWorkspace, recordForm, Row } from './academic-tools';
import { AuthService } from './auth';
import { GuardianFormFields, guardianForm, guardianPayload } from './guardian-fields';
import { PlacementFields, placementForm, placementPayload } from './placement';
import { StudentFormFields, studentFields } from './student-fields';

@Component({imports: [ReactiveFormsModule, MatButtonModule, RouterLink, GuardianFormFields, PlacementFields, StudentFormFields],
  templateUrl: './admission-wizard.html'})
export class AdmissionWizard {
  private readonly api = inject(AdminApi);
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);
  readonly workspace = inject(AcademicWorkspace);
  readonly state = new RequestState();
  readonly step = signal(0);
  readonly steps = ['Student information', 'Guardians', 'Academic placement', 'Documents', 'Review'];
  readonly student = recordForm(studentFields);
  readonly placement = placementForm();
  readonly guardians = signal<ReturnType<typeof guardianForm>[]>([]);
  readonly choices = signal<Row[]>([]);
  readonly sessions = signal<Row[]>([]);
  readonly classes = signal<Row[]>([]);
  readonly sections = signal<Row[]>([]);
  readonly documentTypes = signal<string[]>([]);
  readonly documents = signal<{file: File; kind: string; label: string}[]>([]);
  readonly fileInfo = new FormGroup({
    kind: new FormControl('', {nonNullable: true, validators: Validators.required}),
    label: new FormControl('', {nonNullable: true, validators: Validators.required}),
  });

  constructor() {
    void this.workspace.refresh();
    void this.state.run(async () => {
      const lists = [
        ['accounts.view_sessions', 'academic-sessions', {status: 'active'}, this.sessions],
        ['accounts.view_classes', 'classes', {active: 'true'}, this.classes],
        ['accounts.view_sections', 'sections', {active: 'true'}, this.sections],
        ['students.view_guardian', 'guardians', {}, this.choices],
      ] as const;
      await Promise.all(lists.map(async ([grant, path, params, target]) => {
        if (this.auth.has(grant)) target.set(await this.workspace.options(path, params));
      }));
      const current = this.sessions().find(row => row['is_current']);
      if (current) this.placement.controls.session.setValue(current.id);
      if (this.auth.has('students.add_studentdocument')) {
        this.documentTypes.set((await this.api.read<{kinds: string[]}>('student-document-types/')).kinds);
      }
    });
  }
  canSubmit() {
    return this.auth.has('students.add_student') &&
      this.workspace.can(['students', 'admissions'], 'admissions.add_studentenrollment');
  }

  addGuardian() { this.guardians.update(rows => [...rows, guardianForm()]); }

  back() { this.step.update(value => Math.max(0, value - 1)); }
  removeGuardian(index: number) { this.guardians.update(rows => rows.filter((_, i) => i !== index)); }
  removeDocument(index: number) { this.documents.update(rows => rows.filter((_, i) => i !== index)); }

  selectFile(input: HTMLInputElement) {
    const file = input.files?.[0];
    if (!file || this.fileInfo.invalid || this.documents().length >= 6) return;
    this.documents.update(rows => [...rows, {file, ...this.fileInfo.getRawValue()}]);
    this.fileInfo.reset();
    input.value = '';
  }

  next() {
    this.state.error.set('');
    this.student.markAllAsTouched();
    this.placement.markAllAsTouched();
    const [birth, admission] = [this.student.value['birth_date'], this.student.value['admission_date']];
    try {
      if (this.step() === 0 && (this.student.invalid || String(birth) >= String(admission))) {
        throw new Error('Complete required student fields. Birth date must precede admission.');
      }
      if (this.step() === 1) {
        const links = this.guardians().map(guardianPayload);
        if (links.filter(link => link.primary).length > 1) throw new Error('Choose at most one primary guardian.');
      }
      if (this.step() === 2 && this.placement.invalid) throw new Error('Choose a session and class and check the roll number.');
      this.step.update(value => Math.min(this.steps.length - 1, value + 1));
    } catch (error) {
      this.state.error.set(error instanceof Error ? error.message : 'Review the admission details.');
    }
  }

  async submit() {
    if (this.step() !== 4 || !this.canSubmit() || this.student.invalid || this.placement.invalid) return;
    await this.state.run(async () => {
      const student = this.student.getRawValue();
      if (!student['admission_number']) delete student['admission_number'];
      const form = new FormData();
      const metadata = this.documents().map((item, index) => {
        const field = 'file_' + index;
        form.append(field, item.file);
        return {field, kind: item.kind, label: item.label};
      });
      const data = {student, enrollment: placementPayload(this.placement),
        guardians: this.guardians().map(guardianPayload), documents: metadata};
      form.append('payload', JSON.stringify(data));
      const result = await this.api.write<{student: string}>('POST', 'admissions/', form);
      await this.router.navigate(this.auth.has('accounts.view_student_details') ? ['/students', result.student] : ['/admissions']);
    }, 'Admission saved.');
  }

  display(rows: Row[], id: string) { return rows.find(row => row.id === id)?.['name'] || 'Unassigned'; }
}
