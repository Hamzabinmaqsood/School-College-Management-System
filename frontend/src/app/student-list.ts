import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, csvLink, Row, StudentMetrics } from './academic-tools';
import { AuthService } from './auth';

@Component({imports: [ReactiveFormsModule, MatButtonModule, RouterLink], templateUrl: './student-list.html'})
export class StudentList {
  private readonly api = inject(AdminApi);
  readonly auth = inject(AuthService);
  readonly workspace = inject(AcademicWorkspace);
  readonly admissions = inject(ActivatedRoute).snapshot.data['admissions'] === true;
  readonly resource = this.admissions ? 'admissions' : 'students';
  readonly state = new RequestState();
  readonly rows = signal<Page<Row> | null>(null);
  readonly totals = signal<StudentMetrics | null>(null);
  readonly sessions = signal<Row[]>([]);
  readonly classes = signal<Row[]>([]);
  readonly sections = signal<Row[]>([]);
  readonly form = new FormGroup({
    search: new FormControl('', {nonNullable: true}), session: new FormControl('', {nonNullable: true}),
    academic_class: new FormControl('', {nonNullable: true}), section: new FormControl('', {nonNullable: true}),
    status: new FormControl('', {nonNullable: true}),
  });
  readonly statuses = this.admissions
    ? ['active', 'promoted', 'repeated', 'transferred', 'transferred_out', 'withdrawn', 'graduated']
    : ['active', 'transferred', 'withdrawn', 'graduated'];
  applied: Record<string, string> = {};
  offset = 0;

  constructor() {
    void this.workspace.refresh();
    void this.load();
    this.form.controls.academic_class.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.form.controls.section.reset());
    void this.loadLookups();
    if (!this.admissions) {
      void this.api.read<StudentMetrics>('students/summary/').then(data => this.totals.set(data)).catch(() => undefined);
    }
  }

  async loadLookups() {
    const lookups = [
      ['accounts.view_sessions', 'academic-sessions', this.sessions],
      ['accounts.view_classes', 'classes', this.classes], ['accounts.view_sections', 'sections', this.sections],
    ] as const;
    await Promise.all(lookups.map(async ([grant, endpoint, target]) => {
      if (!this.auth.has(grant)) return;
      try { target.set(await this.workspace.options(endpoint)); }
      catch { this.state.error.set('Filter choices could not be loaded.'); }
    }));
  }

  sectionOptions() {
    const academicClass = this.form.controls.academic_class.value;
    return this.sections().filter(row => !academicClass || row['academic_class'] === academicClass);
  }

  load(offset = 0) {
    this.offset = offset;
    if (!offset) this.applied = this.form.getRawValue();
    const filters = Object.fromEntries(Object.entries(this.applied).filter(([, value]) => value));
    return this.state.run(async () => {
      this.rows.set(await this.api.read<Page<Row>>(this.resource + '/', {offset, ...filters}));
    });
  }

  exportUrl() { return csvLink(this.resource + '/export/', this.applied); }

  canAdmit() {
    return this.auth.has('students.add_student') &&
      this.workspace.can(['admissions', 'students'], 'admissions.add_studentenrollment');
  }
}
