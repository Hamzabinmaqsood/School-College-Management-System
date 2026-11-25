import { Injectable, inject, signal } from '@angular/core';
import { AbstractControl, FormControl, FormRecord, Validators } from '@angular/forms';
import { AdminApi, Page } from './admin';
import { AuthService } from './auth';
import { LicenseStatus } from './license';

export type Value = string | number | boolean | null;
export interface Row { id: string; [key: string]: Value }
export interface Field {
  key: string; label: string; type?: string; required?: boolean; immutable?: boolean;
  lookup?: string; options?: [string, string][]; initial?: Value;
}
export interface StudentMetrics {
  total_students: number; active_students: number; session_name: string | null;
  current_enrollments: number; new_admissions: number;
  class_distribution: {academic_class_id: string; academic_class__name: string; count: number}[];
}

export function permitWrite(status: LicenseStatus | null, features: string[], grants: string[], permission: string) {
  return grants.includes(permission) && !!status?.write_allowed &&
    features.every(feature => status.available_features?.includes(feature));
}

@Injectable({providedIn: 'root'})
export class AcademicWorkspace {
  private readonly api = inject(AdminApi);
  private readonly auth = inject(AuthService);
  readonly license = signal<LicenseStatus | null>(null);

  refresh() {
    return this.api.read<LicenseStatus>('license/status/').then(status => this.license.set(status))
      .catch(() => this.license.set(null));
  }

  can(feature: string | string[], permission: string) {
    return permitWrite(this.license(), typeof feature === 'string' ? [feature] : feature,
      this.auth.user()?.permissions ?? [], permission);
  }

  async options(resource: string, params: Record<string, string> = {}) {
    const rows: Row[] = [];
    let offset = 0;
    for (;;) {
      const page = await this.api.read<Page<Row>>(resource + '/', {...params, limit: 100, offset});
      rows.push(...page.results);
      if (!page.next || !page.results.length) break;
      offset += page.results.length;
    }
    return rows;
  }
}

export function recordForm(fields: Field[], row?: Record<string, Value>) {
  const form = new FormRecord<FormControl<Value>>({});
  for (const field of fields) {
    const value = row?.[field.key] ?? field.initial ?? (field.type === 'checkbox' ? false : '');
    form.addControl(field.key, new FormControl(value, {
      validators: field.required ? Validators.required : [],
    }));
  }
  return form;
}

export function validateDateRange(control: AbstractControl) {
  const start = control.get('start_date')?.value as string | undefined;
  const end = control.get('end_date')?.value as string | undefined;
  return start && end && end <= start ? {dateRange: true} : null;
}

export function sectionsFor(rows: Row[], classId: string) {
  return rows.filter(row => row['academic_class'] === classId && row['active'] !== false);
}

export function csvLink(resource: string, filters: Record<string, string>) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => !!value)).toString();
  return '/api/v1/' + resource + (query ? '?' + query : '');
}
