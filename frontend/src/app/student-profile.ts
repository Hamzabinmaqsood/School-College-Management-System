import { Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, recordForm, Row } from './academic-tools';
import { AuthService } from './auth';
import { GuardianFormFields, guardianForm, guardianPayload } from './guardian-fields';
import { PlacementFields, placementForm, placementPayload } from './placement';
import { StudentFormFields, studentFields } from './student-fields';
import { AttendanceReport } from "./attendance-report";
import { StudentFees } from "./student-fees";
import { StudentResults } from "./student-results";

@Component({imports: [ReactiveFormsModule, MatButtonModule, RouterLink, GuardianFormFields, PlacementFields, StudentFormFields, AttendanceReport, StudentFees, StudentResults],
  templateUrl: './student-profile.html'})
export class StudentProfile {
  private readonly api = inject(AdminApi);
  private readonly route = inject(ActivatedRoute).snapshot;
  readonly auth = inject(AuthService);
  readonly workspace = inject(AcademicWorkspace);
  readonly state = new RequestState();
  readonly id = this.route.paramMap.get('id') ?? '';
  readonly path = 'students/' + this.id + '/';
  readonly printing = this.route.data['print'] === true;
  readonly student = signal<Row | null>(null);
  readonly tab = signal('Overview');
  readonly editing = signal(false);
  readonly links = signal<Page<Row> | null>(null);
  readonly history = signal<Page<Row> | null>(null);
  readonly documents = signal<Page<Row> | null>(null);
  readonly choices = signal<Row[]>([]);
  readonly documentTypes = signal<string[]>([]);
  readonly sessions = signal<Row[]>([]);
  readonly classes = signal<Row[]>([]);
  readonly sections = signal<Row[]>([]);
  readonly studentFields = studentFields;
  readonly linkEditor = signal<'add' | Row | null>(null);
  readonly progression = signal<Row | null>(null);
  readonly progressForm = new FormGroup({
    action: new FormControl('transfer', {nonNullable: true}),
    effective_date: new FormControl('', {nonNullable: true, validators: Validators.required}),
  });
  readonly placement = placementForm();
  readonly upload = new FormGroup({
    kind: new FormControl('', {nonNullable: true, validators: Validators.required}),
    label: new FormControl('', {nonNullable: true, validators: Validators.required}),
  });
  editForm = recordForm(studentFields);
  linkForm = guardianForm();
  offset = 0;

  constructor() {
    void this.workspace.refresh();
    void this.state.run(() => this.loadStudent());
  }

  private async loadStudent() {
    this.student.set(await this.api.read<Row>(this.path + (this.printing ? 'print/' : '')));
  }

  tabs() {
    const tabs = ['Overview'];
    if (this.auth.has('students.view_guardian')) tabs.push('Guardians');
    if (this.auth.has('accounts.view_admissions')) tabs.push('Academic history');
    if (this.auth.has('students.view_studentdocument')) tabs.push('Documents');
    if (this.auth.has("accounts.view_attendance_history")) tabs.push("Attendance");
    if (this.auth.has("fees.view_feeinvoice") && this.auth.has("fees.view_feepayment")) tabs.push("Fees");
    if (this.auth.has("accounts.view_student_results")) tabs.push("Examination results");
    return tabs;
  }

  async show(tab: string) {
    this.tab.set(tab);
    this.linkEditor.set(null);
    this.progression.set(null);
    await this.loadTab(0);
  }

  loadTab(offset = 0) {
    this.offset = offset;
    const panels = {
      Guardians: ['guardians/', this.links], 'Academic history': ['history/', this.history],
      Documents: ['documents/', this.documents],
    } as const;
    const panel = panels[this.tab() as keyof typeof panels];
    if (!panel) return Promise.resolve(true);
    return this.state.run(async () => {
      panel[1].set(await this.api.read<Page<Row>>(this.path + panel[0], {offset}));
      if (this.tab() === 'Documents' && this.auth.has('students.add_studentdocument') && !this.documentTypes().length) {
        this.documentTypes.set((await this.api.read<{kinds: string[]}>('student-document-types/')).kinds);
      }
    });
  }

  edit() {
    this.editForm = recordForm(studentFields, this.student() ?? undefined);
    this.editing.set(true);
  }

  async saveStudent() {
    if (this.editForm.invalid || !this.workspace.can('students', 'students.change_student')) return;
    await this.state.run(async () => {
      const data = this.editForm.getRawValue();
      if (!data['admission_number']) delete data['admission_number'];
      this.student.set(await this.api.write<Row>('PATCH', this.path, data));
      this.editing.set(false);
    }, 'Student details saved.');
  }

  async link(row?: Row) {
    this.linkForm = guardianForm();
    this.linkEditor.set(row ?? 'add');
    if (row) {
      this.linkForm.patchValue({
        relationship: String(row['relationship']), primary: !!row['primary'],
        emergency: !!row['emergency'], pickup: !!row['pickup'],
      });
    } else if (this.auth.has('students.view_guardian')) {
      await this.state.run(async () => this.choices.set(await this.workspace.options('guardians')));
    }
  }

  async saveLink() {
    const selected = this.linkEditor();
    if (!selected || this.linkForm.invalid || !this.workspace.can('students', 'accounts.manage_guardian_links')) return;
    if (await this.state.run(async () => {
      if (selected === 'add') {
        await this.api.write('POST', this.path + 'guardians/', guardianPayload(this.linkForm));
      } else {
        const {relationship, primary, emergency, pickup} = this.linkForm.getRawValue();
        await this.api.write('PATCH', this.path + 'guardians/' + selected.id + '/', {relationship, primary, emergency, pickup});
      }
      this.linkEditor.set(null);
    }, 'Guardian link saved.')) await this.loadTab(this.offset);
  }

  async saveDocument(input: HTMLInputElement) {
    const file = input.files?.[0];
    if (!file || this.upload.invalid || !this.workspace.can('students', 'students.add_studentdocument')) return;
    if (await this.state.run(async () => {
      const payload = new FormData();
      for (const [key, value] of Object.entries(this.upload.getRawValue())) payload.append(key, value);
      payload.append('file', file);
      await this.api.write('POST', this.path + 'documents/', payload);
      this.upload.reset();
      input.value = '';
    }, 'Document saved.')) await this.loadTab();
  }

  async archive(row: Row) {
    if (!await this.api.confirm('Archive this document? It will be removed from ordinary access.')) return;
    if (await this.state.run(async () => {
      await this.api.write('POST', this.path + 'documents/' + row.id + '/archive/', {});
    }, 'Document archived.')) await this.loadTab();
  }

  needsTarget() { return ['promote', 'repeat', 'transfer', 're-enroll'].includes(this.progressForm.controls.action.value); }

  actions(row: Row) {
    return row['status'] === 'active' ? ['transfer', 'promote', 'repeat', 'withdraw', 'transfer-out', 'graduate']
      : ['re-enroll'];
  }

  async beginProgress(row: Row) {
    this.progression.set(row);
    this.progressForm.setValue({action: this.actions(row)[0] ?? 'transfer', effective_date: ''});
    this.placement.reset({session: String(row['session']), academic_class: String(row['academic_class'])});
    await this.state.run(async () => {
      await Promise.all([
        this.workspace.options('academic-sessions', {status: 'active'}).then(rows => this.sessions.set(rows)),
        this.workspace.options('classes', {active: 'true'}).then(rows => this.classes.set(rows)),
        this.workspace.options('sections', {active: 'true'}).then(rows => this.sections.set(rows)),
      ]);
    });
  }

  async saveProgress() {
    const source = this.progression();
    if (!source || this.progressForm.invalid || (this.needsTarget() && this.placement.invalid) ||
        !this.workspace.can('admissions', 'accounts.progress_students')) return;
    if (!await this.api.confirm('Confirm this academic change? The previous enrollment will stay in history.')) return;
    if (await this.state.run(async () => {
      const {action, effective_date} = this.progressForm.getRawValue();
      await this.api.write('POST', 'admissions/' + source.id + '/' + action + '/',
        {effective_date, ...(this.needsTarget() ? {target: placementPayload(this.placement)} : {})});
      this.progression.set(null);
      await this.loadStudent();
    }, 'Academic progression saved.')) await this.loadTab();
  }

  currentPage() {
    return this.tab() === 'Guardians' ? this.links() : this.tab() === 'Academic history' ? this.history()
      : this.tab() === 'Documents' ? this.documents() : null;
  }

  fullName(row: Row) { return row['preferred_name'] || [row['first_name'], row['last_name']].filter(Boolean).join(' '); }
  print() { window.print(); }
}
