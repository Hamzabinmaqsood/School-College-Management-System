import { Component, HostListener, inject, signal } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AcademicWorkspace, Field, Value, recordForm } from './academic-tools';
import { AuthService } from './auth';
import { canExportHrReport, hrForms, hrPages, salaryLine } from './hr-config';

type Entry = Record<string, unknown>;

function newKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2,'0')).join('');
  return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
}

@Component({imports:[FormsModule,ReactiveFormsModule,RouterLink,MatButtonModule],templateUrl:'./hr-page.html'})
export class HrPage {
  readonly api = inject(AdminApi);
  readonly auth = inject(AuthService);
  readonly workspace = inject(AcademicWorkspace);
  readonly route = inject(ActivatedRoute).snapshot;
  readonly page = this.route.data['hrPage'] as string;
  readonly id = this.route.paramMap.get('id');
  readonly title = hrPages[this.page]!;
  readonly menu = Object.entries(hrPages);
  readonly state = new RequestState();
  readonly fields = hrForms[this.page] ?? [];
  readonly form = recordForm(this.fields);
  readonly salaryLine = salaryLine;
  readonly items = signal<ReturnType<typeof recordForm>[]>([]);
  readonly rows = signal<Entry[]>([]);
  readonly details = signal<Entry | null>(null);
  readonly documents = signal<Entry[]>([]);
  readonly employeePayroll = signal<Entry[]>([]);
  readonly assignmentFields: Field[] = [
    {key:'session',label:'Academic session',lookup:'academic-sessions',required:true},
    {key:'academic_class',label:'Class',lookup:'classes',required:true},
    {key:'section',label:'Section',lookup:'sections'}, {key:'subject',label:'Subject',lookup:'subjects'},
    {key:'effective_start',label:'Effective from',type:'date'},
    {key:'effective_end',label:'Effective through',type:'date'},
  ];
  readonly calendarDays = signal<Entry[] | null>(null);

  readonly salaryHistory = signal<{structure: string; name: string; approvals: Entry[]} | null>(null);
  readonly pendingSalary = signal<Page<Entry> | null>(null);
  salaryDecisionReason = '';

  async showSalaryApprovals(structure: string, name: string) {
    this.salaryDecisionReason = '';
    await this.state.run(async () => {
      const approvals = await this.api.read<Entry[]>(this.endpoint + structure + '/approvals/');
      this.salaryHistory.set({structure, name, approvals});
    });
  }

  currentSalaryRevision(structure: string) {
    return this.rows().find(row => row['id'] === structure)?.['revision']
      ?? this.pendingSalary()?.results.find(row => row['structure'] === structure)?.['revision'];
  }

  async showPendingSalary(link: string | null = null) {
    await this.state.run(async () => {
      const offset = link ? Number(new URL(link, location.origin).searchParams.get('offset')) : 0;
      this.pendingSalary.set(await this.api.read<Page<Entry>>(this.endpoint + 'pending-approvals/', {offset}));
    });
  }

  async decideSalary(structure: string, action: 'submit' | 'approve' | 'reject' | 'activate', approval?: unknown, snapshot?: Entry) {
    if (this.state.loading() || this.confirming) return;
    if (action === 'reject' && !this.salaryDecisionReason.trim()) return;
    this.confirming = true;
    try {
      const components = snapshot?.['components'] as Entry[] | undefined;
      const details = snapshot ? [
        `Revision terms for ${snapshot['name']}`,
        `Effective ${snapshot['effective_from'] ?? 'from assignment start'} through ${snapshot['effective_through'] ?? 'assignment end'}`,
        `Basic ${snapshot['basic']}`,
        ...(components ?? []).map(item => `${item['label']} · ${item['kind']} · ${item['amount']}`),
      ] : [];
      if (!await this.api.confirm(['Confirm salary structure ' + action + '?', ...details].join('\n'))) return;
    } finally {
      this.confirming = false;
    }
    await this.state.run(async () => {
      await this.api.write('POST',this.endpoint + structure + '/' + action + '/',
        {approval, reason: this.salaryDecisionReason.trim()});
      this.salaryDecisionReason = '';
      const history = this.salaryHistory();
      if (history?.structure === structure) {
        const approvals = await this.api.read<Entry[]>(this.endpoint + structure + '/approvals/');
        this.salaryHistory.set({...history, approvals});
      }
      if (this.pendingSalary()) {
        this.pendingSalary.set(await this.api.read<Page<Entry>>(this.endpoint + 'pending-approvals/'));
      }
      await this.load(this.offset);
    },'Salary structure action recorded.');
  }

  readonly policyHistory = signal<{id: string; name: string; versions: Entry[]} | null>(null);
  readonly revisionFields = (hrForms['leave-types'] ?? []).filter(field => !['name', 'code'].includes(field.key));
  readonly revisionForm = recordForm(this.revisionFields);
  revisionDate = '';
  revising = false;

  async showPolicyVersions(row: Entry) {
    this.revising = false;
    await this.state.run(async () => {
      const id = String(row['id']);
      const versions = await this.api.read<Entry[]>('hr/leave-types/' + id + '/versions/');
      this.policyHistory.set({id, name: String(row['name']), versions});
    });
  }

  startPolicyRevision(version?: Entry) {
    const basis = version ?? this.policyHistory()?.versions.find(item => item['status'] !== 'draft');
    if (!basis) return;
    this.revisionForm.reset(basis['terms'] as Record<string, Value>);
    this.revisionDate = version ? String(version['effective_start']) : '';
    this.revising = true;
  }

  async savePolicyRevision(draft: boolean) {
    const history = this.policyHistory();
    if (!history || !this.revisionDate || this.revisionForm.invalid) return;
    const terms = this.revisionForm.getRawValue();
    for (const key of ['accrual_start', 'maximum_balance']) {
      if (terms[key] === '') terms[key] = null;
    }
    await this.state.run(async () => {
      const versions = await this.api.write<Entry[]>('POST', 'hr/leave-types/' + history.id + '/versions/',
        {effective_start: this.revisionDate, terms, draft});
      this.policyHistory.set({...history, versions});
      this.revising = false;
    }, draft ? 'Policy draft saved.' : 'Policy revision scheduled.');
  }

  async withdrawPolicyRevision(version: Entry) {
    const history = this.policyHistory();
    if (!history) return;
    await this.state.run(async () => {
      const versions = await this.api.write<Entry[]>('POST',
        'hr/leave-types/' + history.id + '/withdraw-version/', {version: version['id']});
      this.policyHistory.set({...history, versions});
    }, 'Scheduled revision withdrawn.');
  }

  readonly leaveBalance = signal<{balance: string; policy_version?: string; annual_entitlement?: number; preview: Entry[]; ledger: Entry[]} | null>(null);

  async manageLeaveBalance(employee: string, leave_type: string, through: string, command: string, amount: string, reason: string) {
    if (!employee || !leave_type || !through) return;
    const parameters = {employee, leave_type, through};
    await this.state.run(async () => {
      if (command === 'apply') await this.api.write('POST', 'hr/leave-balances/apply/', parameters);
      if (command === 'opening' || command === 'adjustment') {
        await this.api.write('POST', 'hr/leave-balances/adjust/', {...parameters, key: this.requestKey, kind: command, amount, reason});
        this.requestKey = newKey();
      }
      this.leaveBalance.set(await this.api.read('hr/leave-balances/', {...parameters, ...(command === 'preview' ? {preview: '1'} : {})}));
    });
  }

  readonly departmentCalendar = signal<Entry[] | null>(null);

  async loadDepartmentCalendar(department: string, month: string) {
    this.departmentCalendar.set(null);
    await this.state.run(async () => {
      const result = await this.api.read<{totals: Entry[]}>('hr/attendance/calendar/', {department, month});
      this.departmentCalendar.set(result.totals);
    });
  }

  async loadCalendar(employee: string, month: string) {
    if (!employee || !month) return;
    this.calendarDays.set(null);
    await this.state.run(async () => {
      const result = await this.api.read<{days: Entry[]}>('hr/attendance/calendar/', {employee, month});
      this.calendarDays.set(result.days);
    });
  }

  readonly teachingForm = recordForm(this.assignmentFields);
  readonly assignments = signal<Entry[]>([]);
  documentLabel = '';
  documentKind = '';
  documentFile: File | null = null;
  readonly history = signal<Entry[]>([]);
  readonly preview = signal<{entries:Entry[];warnings:Entry[];preview_key:string} | null>(null);
  readonly lookups = signal<Record<string,Entry[]>>({});
  readonly metrics = signal<Entry | null>(null);
  readonly reportNames = ['employees','department-summary','joining-exits','teacher-assignments','attendance','monthly-attendance','leaves','leave-balances','salary-structures','advances','payroll','outstanding-payables','salary-payments','adjustments'];
  report = 'employees';
  readonly reportFilters: Record<string,string> = {from_date:'',to_date:'',department:'',status:''};
  reportParams() {
    return Object.fromEntries(Object.entries(this.reportFilters).filter(([,value]) => value));
  }
  canExportReport() {
    return canExportHrReport(this.report, permission => this.auth.has(permission));
  }

  reportLink(print = false) {
    const params = new URLSearchParams(this.reportParams());
    if (print) params.set('output','print');
    return '/api/v1/' + this.endpoint + 'export/?' + params.toString();
  }
  search = '';
  count = 0;
  offset = 0;
  editing = '';
  requestKey = newKey();
  reason = '';
  confirming = false;
  correctedStatus = "present";
  readonly feature = ['overtime','overtime-policies','salary-structures','salary-assignments','advances','periods','payroll','salary-payments','payroll-adjustments'].includes(this.page) ? 'payroll' : 'hr';

  constructor() {
    void this.workspace.refresh();
    void this.state.run(async () => {
      await this.load();
      if (this.page === 'salary-payments' && this.route.queryParamMap.has('entry')) {
        this.form.controls['entry']?.setValue(this.route.queryParamMap.get('entry'));
      }
      const names = new Set(this.fields.flatMap(field => field.lookup ? [field.lookup] : []));
      if (this.page === "reports" || (this.page === "attendance" && this.auth.has("accounts.view_staff"))) names.add("departments");
      const options: Record<string,Entry[]> = {};
      await Promise.all([...names].map(async name => {
        options[name] = (await this.api.read<Page<Entry>>('hr/' + name + '/', {limit:100})).results;
      }));
      this.lookups.update(previous => ({...previous,...options}));
    });
    this.form.valueChanges.subscribe(() => this.preview.set(null));
  }

  can(permission: string) { return this.workspace.can(this.feature,permission); }
  get endpoint() { return 'hr/' + (this.page === 'teachers' ? 'employees' : this.page === 'reports' ? 'reports/' + this.report : this.page) + '/'; }

  async load(offset = 0) {
    if (this.page === 'settings') {
      const values = await this.api.read<Record<string,Value>>('hr/settings/');
      this.form.reset(Object.fromEntries(this.fields.map(field => [field.key, field.key === 'document_retention_by_kind' ? JSON.stringify(values[field.key] ?? {}) : values[field.key] ?? ''])));
      return;
    }
    if (this.page === 'overview') {
      this.metrics.set(await this.api.read<Entry>('hr/overview/'));
      return;
    }
    if (this.id) { await this.open(this.id); return; }
    const response = await this.api.read<Page<Entry>>(this.endpoint,{
      limit:25,offset,search:this.search,...(this.page === 'reports' ? this.reportParams() : {}),...(this.page === 'teachers' && {designation__teaching:'true'}),
    });
    this.rows.set(response.results);
    this.count = response.count;
    this.offset = offset;
  }

  async open(id: string) {
    this.details.set(await this.api.read<Entry>(this.endpoint + id + '/'));
    if (this.page !== 'employees') return;
    const tasks: Promise<unknown>[] = [
      this.api.read<Entry[]>(this.endpoint + id + '/history/').then(data => this.history.set(data)),
    ];
    if (this.auth.has('accounts.view_employee_documents')) tasks.push(
      this.api.read<Page<Entry>>('hr/documents/', {employee:id,limit:100}).then(data => this.documents.set(data.results)));
    if (this.auth.has('accounts.view_payroll')) tasks.push(
      this.api.read<Page<Entry>>(this.endpoint + id + '/payslips/',{limit:100}).then(data => this.employeePayroll.set(data.results)));
    if (this.auth.has('accounts.view_teachers')) tasks.push(
      this.api.read<Entry[]>(this.endpoint + id + '/assignments/').then(data => this.assignments.set(data)));
    if (this.auth.has('accounts.manage_teaching_assignments') && this.auth.has('accounts.view_teachers')) {
      tasks.push(Promise.all(this.assignmentFields.map(async field => {
        const path = field.lookup!;
        const grants: Record<string,string> = {'academic-sessions':'accounts.view_sessions',
          classes:'accounts.view_classes',sections:'accounts.view_sections',subjects:'accounts.view_subjects'};
        if (!this.auth.has(grants[path]!)) return;
        const rows = (await this.api.read<Page<Entry>>(path + '/', {limit:100})).results;
        this.lookups.update(previous => ({...previous,[path]:rows}));
      })));
    }
    await Promise.all(tasks);
  }

  async assignTeacher() {
    if (!this.id || this.teachingForm.invalid) return;
    const data = this.teachingForm.getRawValue();
    await this.state.run(async () => {
      await this.api.write('POST',this.endpoint + this.id + '/assignments/', {
        ...data, section:data['section'] || null,subject:data['subject'] || null,
        effective_start:data['effective_start'] || null, effective_end:data['effective_end'] || null,
      });
      this.teachingForm.markAsPristine();
      await this.open(this.id!);
    },'Teaching assignment saved.');
  }

  readonly assignmentHistory = signal<Record<string, Entry[]>>({});

  showAssignmentHistory(assignment: string) {
    return this.state.run(async () => {
      const page = await this.api.read<Page<Entry>>(this.endpoint + this.id + '/assignment-history/', {assignment});
      this.assignmentHistory.update(items => ({...items, [assignment]: page.results}));
    });
  }

  async updateAssignmentDates(assignment: unknown, from: string, through: string) {
    await this.state.run(async () => {
      await this.api.write('PATCH', this.endpoint + this.id + '/assignment-dates/', {
        assignment, effective_start: from || null, effective_end: through || null,
      });
      await this.open(this.id!);
    }, 'Assignment dates saved.');
  }

  async deactivateTeaching(row: Entry) {
    if (!this.id || !await this.api.confirm('Deactivate this teaching assignment?')) return;
    await this.state.run(async () => {
      await this.api.write('POST',this.endpoint + this.id + '/deactivate-assignment/',{assignment:row['id']});
      await this.open(this.id!);
    },'Teaching assignment deactivated.');
  }

  async uploadDocument() {
    if (!this.documentFile || !this.id || !this.documentLabel.trim() || !this.documentKind.trim()) return;
    const form = new FormData();
    form.set('file',this.documentFile);
    form.set('employee',this.id);
    form.set('label',this.documentLabel);
    form.set('kind',this.documentKind);
    await this.state.run(async () => {
      await this.api.write('POST','hr/documents/',form);
      this.documentFile = null;
      await this.open(this.id!);
    },'Document uploaded.');
  }

  readonly retentionReviews = signal<Record<string, Entry[]>>({});

  async reviewDocument(documentId: string, operation: string, reason: string, date: string) {
    await this.state.run(async () => {
      await this.api.write('POST', 'hr/documents/' + documentId + '/retention/', {
        operation, reason, review_on: date || null,
      });
      await this.open(this.id!);
      await this.loadRetentionReviews(documentId);
    }, 'Retention review recorded.');
  }

  async loadRetentionReviews(documentId: string) {
    const result = await this.api.read<Page<Entry>>('hr/documents/' + documentId + '/reviews/');
    this.retentionReviews.update(current => ({...current, [documentId]: result.results}));
  }

  async showRetentionReviews(documentId: string) {
    await this.state.run(() => this.loadRetentionReviews(documentId));
  }

  async archiveDocument(id: unknown) {
    if (!this.id || !await this.api.confirm('Archive this employee document?')) return;
    await this.state.run(async () => {
      await this.api.write('POST','hr/documents/' + id + '/archive/',{});
      await this.open(this.id!);
    },'Document archived.');
  }

  reload(offset = 0) { return this.state.run(() => this.load(offset)); }
  leave() { return !(this.form.dirty || this.teachingForm.dirty) || this.api.confirm('Discard unsaved changes?'); }

  @HostListener('window:beforeunload', ['$event'])
  warn(event: BeforeUnloadEvent) {
    if (this.form.dirty || this.teachingForm.dirty) { event.preventDefault(); event.returnValue = ''; }
  }

  columns(row: Entry) {
    return Object.keys(row).filter(key => !['id','created_at','updated_at','items','components','key','reference','current_approval','legacy_active'].includes(key));
  }
  label(key: string) { return key.replaceAll('_',' ').replaceAll('-',' '); }
  options(field: Field) { return this.lookups()[field.lookup ?? ''] ?? []; }
  name(row: Entry) { return (row['name'] ?? row['display_name']) || [row['code'],row['first_name'],row['last_name']].filter(Boolean).join(' · '); }

  payload() {
    const data: Entry = this.form.getRawValue();
    if (this.page === "employees" && data["code"] === "") delete data["code"];
    for (const key of ['user','ended_on','check_in','check_out','shift_start','shift_end','department','document_retention_days','monthly_divisor','accrual_start','maximum_balance','effective_from','effective_through']) {
      if (data[key] === '') data[key] = null;
    }
    for (const key of ['unpaid_leave_daily_rate','carry_limit','carry_expiry_days','break_minutes','late_tolerance_minutes','early_tolerance_minutes']) {
      if (data[key] === '' || data[key] === null) delete data[key];
    }
    if (this.page === 'settings') {
      const policy = String(data['document_retention_by_kind'] ?? '').trim();
      try {
        data['document_retention_by_kind'] = JSON.parse(policy || '{}');
      } catch {
        throw new Error('Enter a JSON object mapping document types to retention days.');
      }
    }
    for (const key of ['default_schedule','leave_entitlements']) {
      if (key in data) {
        try {
          data[key] = JSON.parse(String(data[key] || '{}'));
        } catch {
          throw new Error('Enter a valid JSON object for ' + this.label(key) + '.');
        }
      }
    }
    if (this.page === 'contracts') data['weekdays'] = String(data['weekdays']).split(',').filter(Boolean).map(Number);
    if (this.page === 'salary-structures') data['components'] = this.items().map(row => row.getRawValue());
    if (this.page === 'advances') data['reference'] = this.requestKey;
    if (['payroll','salary-payments','payroll-adjustments'].includes(this.page)) data['key'] = this.requestKey;
    return data;
  }

  edit(row: Entry) {
    this.editing = String(row['id']);
    this.form.reset(Object.fromEntries(this.fields.map(field => [field.key,
      (['default_schedule','leave_entitlements'].includes(field.key) ? JSON.stringify(row[field.key] ?? {}) : row[field.key] ?? field.initial ?? '') as Value])));
    if (this.page === 'salary-structures') {
      const components = (row['components'] ?? []) as Record<string, Value>[];
      this.items.set(components.map(component => {
        const form = recordForm(salaryLine);
        form.patchValue({ label: component['label'] ?? '', kind: component['kind'] ?? '', amount: component['amount'] ?? '' });
        return form;
      }));
    }
  }

  addLine() { this.items.update(current => [...current,recordForm(this.salaryLine)]); }
  deleteLine(index: number) { this.items.update(rows => rows.filter((_,position) => index !== position)); }

  get editable() {
    if (this.page === 'employees' && this.editing) return this.can('accounts.change_employee');
    return !!this.title[2] && this.can(this.title[2]);
  }

  async save() {
    if (!this.editable || this.state.loading() || this.form.invalid || this.items().some(row => row.invalid)) return;
    this.state.success.set('');
    if (this.page === 'payroll') {
      await this.state.run(async () => this.preview.set(await this.api.write('POST',this.endpoint + 'preview/',this.payload())));
      return;
    }
    if (this.page === 'salary-payments' || this.page === 'payroll-adjustments') {
      if (this.confirming) return;
      this.confirming = true;
      try {
        if (!await this.api.confirm('Record this salary transaction?')) return;
      } finally {
        this.confirming = false;
      }
    }
    const id = this.editing;
    const result = await this.state.run(async () => {
      await this.api.write(id || this.page === 'settings' ? 'PATCH' : 'POST',this.endpoint + (id ? id + '/' : ''),this.payload());
      this.form.markAsPristine();
      this.requestKey = newKey();
      await this.load();
    },'Record saved.');
    if (result && this.page !== 'settings') {
      this.editing = '';
      this.form.reset(recordForm(this.fields).getRawValue());
      this.items.set([]);
    }
  }

  async generate() {
    if (!this.preview()?.entries.length || this.state.loading() || !await this.api.confirm('Generate this draft payroll?')) return;
    await this.state.run(async () => {
      await this.api.write('POST',this.endpoint + 'generate/',{...this.payload(),preview_key:this.preview()?.preview_key});
      this.preview.set(null);
      this.form.markAsPristine();
      this.requestKey = newKey();
      await this.load();
    },'Draft payroll generated.');
  }

  readonly attendanceCorrections = signal<Entry[] | null>(null);

  showAttendanceCorrections(id: string) {
    this.attendanceCorrections.set(null);
    return this.state.run(async () => {
      const page = await this.api.read<Page<Entry>>('hr/attendance/' + id + '/corrections/');
      this.attendanceCorrections.set(page.results);
    });
  }

  async move(row: Entry, action: string, body: Entry = {}) {
    if (this.state.loading() || !await this.api.confirm('Confirm ' + action + '?')) return;
    await this.state.run(async () => {
      await this.api.write('POST',this.endpoint + row['id'] + '/' + action + '/',body);
      this.reason = '';
      await this.load(this.offset);
    },'Change recorded.');
  }

  entries(row: Entry) { return (row['entries'] as Page<Entry> | undefined)?.results ?? []; }
  formatCorrection(value: unknown) {
    return Object.entries((value ?? {}) as Entry).map(([key, detail]) => this.label(key) + ": " + this.format(detail)).join(", ");
  }
  format(value: unknown) { return value === null ? '—' : value; }
}
