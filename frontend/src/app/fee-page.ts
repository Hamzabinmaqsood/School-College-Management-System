import { Component, inject, signal } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, Field, recordForm, Value } from './academic-tools';
import { AuthService } from './auth';
import { feePages, lineFields, registrationFields } from './fee-config';

type Entry = Record<string, unknown>;
function transactionKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}

export function minorUnits(value: string) {
  if (!/^\d{1,12}(\.\d{1,2})?$/.test(value)) return null;
  const [major, fraction = ''] = value.split('.');
  return BigInt(major!) * 100n + BigInt(fraction.padEnd(2, '0'));
}
function moneyText(value: bigint) {
  return (value / 100n).toString() + '.' + (value % 100n).toString().padStart(2, '0');
}

@Component({
  imports: [FormsModule, ReactiveFormsModule, MatButtonModule, RouterLink],
  templateUrl: './fee-page.html',
})
export class FeePage {
  readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute).snapshot;
  readonly api = inject(AdminApi);
  readonly workspace = inject(AcademicWorkspace);
  readonly state = new RequestState();
  readonly kind = this.route.data['feePage'] as string;
  readonly config = feePages[this.kind]!;
  readonly menu = Object.entries(feePages);
  readonly fields = registrationFields[this.kind] ?? [];
  readonly lineFields = lineFields;
  readonly form = recordForm(this.fields);
  readonly lines = signal([recordForm(this.lineFields)]);
  readonly rows = signal<Entry[]>([]);
  readonly lookups = signal<Record<string, Entry[]>>({});
  readonly overview = signal<Entry | null>(null);
  readonly preview = signal<Entry | null>(null);
  readonly receipt = signal('');
  readonly columns = signal<string[]>([]);
  readonly count = signal(0);
  readonly filter = {search: '', from_date: '', to_date: '', session: '', academic_class: '', section: '', method: ''};
  readonly reports = ['collections', 'monthly', 'outstanding', 'aging', 'defaulters', 'class-summary',
    'session-summary', 'student-ledger', 'methods', 'invoices', 'receipts', 'structures', 'concessions', 'refunds'];
  readonly collection = recordForm([
    {key:'student', label:'Student', required:true}, {key:'date', label:'Payment date', required:true},
    {key:'method', label:'Method', required:true}, {key:'external_reference', label:'External reference'},
  ]);
  readonly allocations = signal<Record<string, string>>({});
  readonly correction = signal<{path: string; permission: string; row: Entry} | null>(null);
  userSearch = '';
  report = 'collections';
  offset = 0;
  editing = '';
  reason = '';
  paymentKey = transactionKey();
  paymentFingerprint = '';
  confirming = false;
  correctionKey = transactionKey();
  correctionFingerprint = '';
  billingPayload: Entry | null = null;
  date = '';
  methods: string[] = [];

  constructor() {
    void this.workspace.refresh();
    void this.state.run(async () => {
      const tasks: Promise<unknown>[] = [this.load()];
      if (this.fields.some(field => field.lookup) || ['collect', 'reports', 'outstanding'].includes(this.kind)) {
        tasks.push(this.loadLookups());
      }
      await Promise.all(tasks);
      const student = this.route.queryParamMap.get('student');
      if (student && this.kind === 'collect') {
        this.collection.controls['student']?.setValue(student);
        await this.openInvoices();
      }
    });
    this.form.valueChanges.subscribe(() => { this.preview.set(null); this.billingPayload = null; });
  }

  can(grant: string) { return this.workspace.can('fees', grant); }

  get canEdit() { return !!this.config[2] && this.can(this.config[2]); }

  parameters() {
    return Object.fromEntries(Object.entries(this.filter).filter(([, value]) => value));
  }

  async load(offset = 0) {
    if (this.kind === 'collect') return;
    if (this.kind === 'overview') {
      this.overview.set(await this.api.read<Entry>('fees/overview/'));
      return;
    }
    if (this.kind === 'settings') {
      const config = await this.api.read<Entry>('fees/settings/');
      this.populate({...config, payment_methods: (config['payment_methods'] as string[]).join(', ')});
      return;
    }
    if (this.kind === 'billing' && !this.auth.has('fees.view_feeinvoice')) return;
    const endpoint = this.kind === 'billing' ? 'billing/history' :
      this.kind === 'reports' ? 'reports/' + this.report :
      this.kind === 'outstanding' ? 'reports/outstanding' : this.kind;
    const params = {...this.parameters(), offset, limit: 25};
    const page = await this.api.read<Page<Entry>>('fees/' + endpoint + '/', params);
    this.setRows(page.results);
    this.offset = offset;
    this.count.set(page.count);
  }

  setRows(rows: Entry[]) {
    this.rows.set(rows);
    const hidden = ['id', 'invoice_id', 'student_id', 'student', 'session', 'enrollment', 'details', 'items', 'allocations', 'approved_by'];
    const visible = Object.keys(rows[0] ?? {}).filter(key => !hidden.includes(key));
    if (this.kind === 'outstanding' || this.kind === 'reports') {
      if (Object.hasOwn(rows[0] ?? {}, 'student')) visible.splice(2, 0, 'student');
    }
    this.columns.set(visible);
  }

  reload(offset = 0) { return this.state.run(() => this.load(offset)); }

  async loadLookups() {
    const data = await this.api.read<Record<string, unknown>>('fees/lookups/', this.userSearch
      ? {search: this.userSearch} : {});
    const values = Object.fromEntries(Object.entries(data).filter(([, item]) => Array.isArray(item)));
    for (const resource of ['categories', 'structures', 'invoices']) {
      if (this.fields.some(field => field.lookup === resource) ||
          (resource === 'categories' && this.kind === 'structures')) {
        values[resource] = (await this.api.read<Page<Entry>>('fees/' + resource + '/', {limit:100})).results;
      }
    }
    this.lookups.set(values as Record<string, Entry[]>);
    this.date = String(data['date']);
    this.methods = data['methods'] as string[];
    if (!this.collection.controls['date']?.value) this.collection.controls['date']?.setValue(this.date);
  }

  searchStudents() { return this.state.run(() => this.loadLookups()); }

  option(row: Entry) {
    return row['name'] || row['number'] || [row['first_name'] || row['student__first_name'],
      row['last_name'], row['admission_number'] || row['student__admission_number'],
      row['academic_class__name'], row['session__name']].filter(Boolean).join(' · ');
  }

  populate(row: Entry) {
    this.form.reset(Object.fromEntries(this.fields.map(field => [
      field.key, (row[field.key] ?? field.initial ?? '') as Value,
    ])));
  }

  payload() {
    const data: Entry = this.form.getRawValue();
    if (this.kind === 'structures') {
      data['items'] = this.lines().map(line => line.getRawValue());
    }
    if (this.kind === 'assignments' || this.kind === 'structures' || this.kind === 'concessions') {
      for (const key of ['section', 'structure', 'category', 'amount']) {
        if (data[key] === '') data[key] = null;
      }
    }
    if (this.kind === 'billing') {
      data['period'] = String(data['period']) + '-01';
      return Object.fromEntries(Object.entries(data).filter(([, value]) => value));
    }
    if (this.kind === 'settings') data['payment_methods'] = String(data['payment_methods']).split(',')
      .map(value => value.trim()).filter(Boolean);
    if (['adjustments','refunds'].includes(this.kind)) data['idempotency_key'] = this.correctionKey;
    if (this.kind === 'assignments' && this.editing) return {active: data['active']};
    return data;
  }

  edit(row: Entry) {
    this.editing = String(row['id']);
    this.populate(row);
    if (this.kind === 'structures') this.lines.set((row['items'] as Record<string, Value>[])
      .map(item => recordForm(this.lineFields, item)));
  }

  mayEdit(row: Entry) {
    return this.canEdit && ['categories','structures','assignments','concessions'].includes(this.kind) &&
      (this.kind !== 'structures' || row['status'] === 'draft') &&
      (this.kind !== 'concessions' || row['status'] === 'pending');
  }

  label(key: string) { return key.replaceAll('__', ' ').replaceAll('_', ' '); }

  display(value: unknown) {
    return value === null || value === undefined ? '—' :
      Array.isArray(value) ? value.join(', ') : String(value);
  }

  copyDraft(row: Entry) {
    this.edit(row);
    this.editing = '';
    this.form.controls['name']?.setValue(String(row['name']) + ' copy');
  }

  chartRows(value: unknown) {
    return Array.isArray(value) ? value as Entry[] : [];
  }

  chartValue(value: unknown) {
    return minorUnits(String(value).replace(/^-/, '')) ?? 0n;
  }

  chartPercent(value: unknown, entries: Entry[]) {
    const max = entries.reduce((largest, row) => {
      const current = this.chartValue(row['amount'] ?? row['outstanding']);
      return current > largest ? current : largest;
    }, 0n);
    return max ? Number(this.chartValue(value) * 100n / max) : 0;
  }

  async save() {
    if (!this.canEdit || this.form.invalid || (this.kind === 'structures' && this.lines().some(line => line.invalid))) return;
    const path = 'fees/' + this.kind + '/' + (this.editing ? this.editing + '/' : '');
    const body = this.payload();
    if (['adjustments','refunds'].includes(this.kind)) {
      const fingerprint = JSON.stringify(body);
      if (this.correctionFingerprint && this.correctionFingerprint !== fingerprint) {
        this.state.error.set('Retry the original correction values or verify the recorded transaction.');
        return;
      }
      this.correctionFingerprint = fingerprint;
    }
    const success = await this.state.run(async () => {
      await this.api.write(this.editing || this.kind === 'settings' ? 'PATCH' : 'POST', path, body);
      this.correctionKey = transactionKey();
      this.correctionFingerprint = '';
      await this.load();
    }, 'Saved.');
    if (success && this.kind !== 'settings') {
      this.editing = '';
      this.populate({});
      this.lines.set([recordForm(this.lineFields)]);
    }
  }

  async previewBills() {
    if (this.form.invalid) return;
    const data = this.payload();
    await this.state.run(async () => {
      const result = await this.api.write<Entry>('POST', 'fees/billing/preview/', data);
      this.billingPayload = {...data, preview_key: result['preview_key']};
      this.preview.set(result);
    });
  }

  async generate() {
    if (!this.billingPayload || !this.canEdit || !await this.ask('Issue the previewed fee bills?')) return;
    const data = this.billingPayload;
    await this.state.run(async () => {
      this.preview.set(await this.api.write<Entry>('POST', 'fees/billing/generate/', data));
      this.billingPayload = null;
      await this.load();
    }, 'Billing completed.');
  }

  async readOutstanding() {
    const id = this.collection.controls['student']?.value;
    this.setRows(id ? await this.api.read<Entry[]>('fees/students/' + id + '/outstanding/') : []);
  }

  async openInvoices() {
    this.allocations.set({});
    this.paymentFingerprint = '';
    this.paymentKey = transactionKey();
    this.receipt.set('');
    await this.readOutstanding();
  }

  changeStudent(id: string) {
    this.collection.controls['student']?.setValue(id);
    return this.state.run(() => this.openInvoices());
  }

  allocation(id: string, value: string) {
    this.allocations.update(data => ({...data, [id]: value}));
  }

  payment() {
    let total = 0n;
    const allocations = [];
    for (const row of this.rows()) {
      const invoice = String(row['id']);
      const value = this.allocations()[invoice];
      if (!value) continue;
      const amount = minorUnits(value);
      const balance = minorUnits(String(row['outstanding']));
      if (amount === null || balance === null || amount > balance) return null;
      if (!amount) continue;
      total += amount;
      allocations.push({invoice, amount: moneyText(amount)});
    }
    return allocations.length ? {...this.collection.getRawValue(), amount: moneyText(total), allocations} : null;
  }

  async ask(message: string) {
    if (this.confirming || this.state.loading()) return false;
    this.confirming = true;
    try {
      return await this.api.confirm(message);
    } finally {
      this.confirming = false;
    }
  }

  async post() {
    const data = this.payment();
    if (!data || this.collection.invalid || !this.canEdit ||
        !await this.ask('Post payment of PKR ' + data.amount + '?')) return;
    const fingerprint = JSON.stringify(data);
    if (this.paymentFingerprint && this.paymentFingerprint !== fingerprint) {
      this.state.error.set('Retry the original payment values or verify the transaction in Payment history before restarting collection.');
      return;
    }
    this.paymentFingerprint = fingerprint;
    await this.state.run(async () => {
      const result = await this.api.write<Entry>('POST', 'fees/payments/', {...data, idempotency_key: this.paymentKey});
      this.receipt.set(String(result['id']));
      this.allocations.set({});
      this.paymentKey = transactionKey();
      this.paymentFingerprint = '';
      this.setRows([]);
      await this.readOutstanding();
    }, 'Payment posted.');
  }

  async action(row: Entry, path: string, permission: string, requiresReason = false) {
    if (!this.can(permission)) return;
    if (requiresReason) {
      this.reason = '';
      this.correction.set({path, permission, row});
    } else if (await this.ask('Apply this change?')) {
      await this.runAction(row, path, {});
    }
  }

  async runAction(row: Entry, path: string, body: Entry) {
    await this.state.run(async () => {
      await this.api.write('POST', 'fees/' + this.kind + '/' + row['id'] + '/' + path + '/', body);
      this.correction.set(null);
      await this.load();
    }, 'Change recorded.');
  }

  reportLink(print = false) {
    const query = new URLSearchParams(this.parameters());
    if (print) query.set('format_type', 'print');
    return '/api/v1/fees/reports/' + (this.kind === 'outstanding' ? 'outstanding' : this.report)
      + '/export/?' + query.toString();
  }

  addLine() { this.lines.update(lines => [...lines, recordForm(this.lineFields)]); }

  removeLine(index: number) { this.lines.update(lines => lines.filter((_, position) => position !== index)); }

  choices(field: Field) { return this.lookups()[field.lookup ?? ''] ?? []; }
}
