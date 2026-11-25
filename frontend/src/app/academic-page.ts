import { Component, inject, signal } from '@angular/core';
import { FormControl, FormRecord, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { ActivatedRoute } from '@angular/router';
import { AdminApi, Page, RequestState } from './admin';
import { registries } from './academic-config';
import { AcademicWorkspace, Field, recordForm, Row, validateDateRange, Value } from './academic-tools';
import { AuthService } from './auth';

@Component({imports: [ReactiveFormsModule, MatButtonModule], templateUrl: './academic-page.html'})
export class AcademicPage {
  private readonly api = inject(AdminApi);
  readonly workspace = inject(AcademicWorkspace);
  readonly auth = inject(AuthService);
  readonly registry = registries[inject(ActivatedRoute).snapshot.data['registry'] as string]!;
  readonly state = new RequestState();
  readonly page = signal<Page<Row> | null>(null);
  readonly edit = signal<Row | null>(null);
  readonly editorOpen = signal(false);
  readonly options = signal<Record<string, Row[]>>({});
  readonly search = new FormControl('', {nonNullable: true});
  readonly filter = new FormControl('', {nonNullable: true});
  readonly sort = new FormControl('', {nonNullable: true});
  readonly groupFilter = new FormControl('', {nonNullable: true});
  readonly policyFields: Field[] = [
    {key: 'prefix', label: 'Admission prefix', required: true},
    {key: 'padding', label: 'Number padding', type: 'number', required: true},
    {key: 'allow_unsectioned', label: 'Allow enrollment without a section', type: 'checkbox'},
  ];
  policy = signal<FormRecord<FormControl<Value>> | null>(null);
  form = recordForm(this.registry.fields);
  offset = 0;

  constructor() {
    void this.workspace.refresh();
    void this.load();
    void this.loadOptions();
  }

  private async loadOptions() {
    const allowed: Record<string, string> = {'academic-sessions': 'accounts.view_sessions',
      classes: 'accounts.view_classes', subjects: 'accounts.view_subjects'};
    const resources = [...new Set(this.registry.fields.flatMap(field =>
      field.lookup && this.auth.has(allowed[field.lookup] ?? '') ? [field.lookup] : []))];
    try {
      this.options.set(Object.fromEntries(await Promise.all(resources.map(async resource =>
        [resource, await this.workspace.options(resource)] as const))));
    } catch {
      this.state.error.set('Lookup choices could not be loaded.');
    }
  }

  load(offset = 0) {
    this.offset = offset;
    return this.state.run(async () => {
      this.page.set(await this.api.read<Page<Row>>(this.registry.resource + '/', {
        search: this.search.value, offset, ...(this.registry.filter?.key && this.filter.value
          ? {[this.registry.filter.key]: this.filter.value} : {}),
        ...(this.sort.value ? {ordering: this.sort.value} : {}),
        ...(this.groupFilter.value ? {academic_class: this.groupFilter.value} : {}),
      }));
    });
  }

  can(permission: string) { return this.workspace.can(this.registry.feature, permission); }

  display(row: Row, key: string) {
    const value = row[key];
    if (key === 'active') return value ? 'Active' : 'Inactive';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    return value ?? '—';
  }

  begin(row?: Row) {
    this.edit.set(row ?? null);
    this.form = recordForm(this.registry.fields, row);
    if (this.registry.resource === 'academic-sessions') this.form.addValidators(validateDateRange);
    if (row) for (const field of this.registry.fields) {
      if (field.immutable) this.form.controls[field.key]?.disable();
    }
    this.editorOpen.set(true);
  }

  async save() {
    this.form.markAllAsTouched();
    if (this.form.invalid) return;
    const row = this.edit();
    if (!this.can(row ? this.registry.change : this.registry.add)) return;
    const values = {...this.form.value};
    for (const field of this.registry.fields) {
      if ((field.lookup || field.type === 'number') && values[field.key] === '') values[field.key] = null;
    }
    if (row && (values['status'] === 'closed' && row['status'] !== 'closed' ||
        values['active'] === false && row['active'] === true) &&
        !await this.api.confirm('Confirm this status change? Historical records are retained.')) return;
    if (await this.state.run(async () => {
      await this.api.write(row ? 'PATCH' : 'POST', this.registry.resource + '/' + (row ? row.id + '/' : ''), values);
      this.editorOpen.set(false);
    }, 'Record saved.')) await this.load(this.offset);
  }

  async setCurrent(row: Row) {
    if (!await this.api.confirm('Set this active session as current?')) return;
    if (await this.state.run(async () => {
      await this.api.write('POST', 'academic-sessions/' + row.id + '/set-current/', {});
    }, 'Current session updated.')) await this.load(this.offset);
  }

  async openPolicy() {
    await this.state.run(async () => this.policy.set(recordForm(this.policyFields,
      await this.api.read<Record<string, Value>>('admission-policy/'))));
  }

  async savePolicy() {
    const policy = this.policy();
    if (!policy || policy.invalid || !this.workspace.can('academics', 'accounts.manage_admissions_policy')) return;
    await this.state.run(async () => {
      await this.api.write('PATCH', 'admission-policy/', policy.getRawValue());
      this.policy.set(null);
    }, 'Admission policy saved.');
  }
}
