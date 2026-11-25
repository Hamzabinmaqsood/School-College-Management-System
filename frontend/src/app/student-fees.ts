import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AdminApi, RequestState } from './admin';
import { AuthService } from './auth';

interface Invoice {
  id: string; number: string; period: string; total: string; paid: string; outstanding: string;
  status: string; due_date: string;
}
interface Payment {id: string; number: string; date: string; amount: string; reversed: boolean}
interface Statement {
  invoices: Invoice[]; payments: Payment[]; outstanding: string; overdue: string;
  invoiced: string; paid: string; plans: string[]; concessions: string[];
  adjustments: {id: string; kind: string; amount: string; approved: boolean}[];
}

@Component({
  selector: 'app-student-fees',
  imports: [RouterLink],
  template: '<section class="panel"><h2>Fee statement</h2>' + 
    '@if (state.loading()) { <p role="status">Loading fee statement…</p> }' +
    '@if (state.error()) { <p role="alert">{{ state.error() }}</p> }' +
    '@if (statement(); as data) {' +
    ' <p>Invoiced PKR {{ data.invoiced }} · Paid PKR {{ data.paid }} · Outstanding PKR {{ data.outstanding }} · Overdue PKR {{ data.overdue }}</p>' +
    ' @if (data.plans.length) { <p>Fee plans: {{ data.plans.join(", ") }}</p> }' +
    ' @if (data.concessions.length) { <p>Current concessions: {{ data.concessions.join(", ") }}</p> }' +
    ' @if (auth.has("accounts.collect_fees")) { <a routerLink="/fees/collect" [queryParams]="{student: studentId}">Collect payment</a> }' +
    ' @if (auth.has("accounts.export_fee_reports")) { <a [href]="exportLink()">Download statement</a> }' +
    ' <h3>Invoices</h3><div class="attendance-rows">' +
    ' @for (row of data.invoices; track row.id) { <article><strong>{{ row.number }}</strong><p>{{ row.period }} · {{ row.status }}</p>' +
    ' <p>PKR {{ row.total }} charged · PKR {{ row.outstanding }} outstanding</p>' +
    ' @if (auth.has("accounts.print_fee_challan")) { <a [href]="challan(row.id)" target="_blank" rel="noopener">View challan</a> }</article>' +
    ' } @empty { <p>No invoices recorded.</p> }</div>' +
    ' <h3>Payments</h3><div class="attendance-rows">' +
    ' @for (row of data.payments; track row.id) { <article><strong>{{ row.number }}</strong><p>{{ row.date }} · PKR {{ row.amount }} · {{ row.reversed ? "Reversed" : "Posted" }}</p>' +
    ' @if (auth.has("accounts.print_fee_receipt")) { <a [href]="receipt(row.id)" target="_blank" rel="noopener">View receipt</a> }</article>' +
    ' } @empty { <p>No payments recorded.</p> }</div>' +
    ' @if (data.adjustments.length) { <h3>Adjustments</h3>' +
    ' @for (row of data.adjustments; track row.id) { <p>{{ row.kind }} · PKR {{ row.amount }} · {{ row.approved ? "Approved" : "Pending" }}</p> } }' +
    '}</section>',
})
export class StudentFees implements OnInit {
  @Input({required:true}) studentId = '';
  readonly auth = inject(AuthService);
  readonly state = new RequestState();
  readonly statement = signal<Statement | null>(null);
  private readonly api = inject(AdminApi);

  ngOnInit() {
    void this.state.run(async () => this.statement.set(
      await this.api.read<Statement>('fees/students/' + this.studentId + '/statement/')));
  }

  exportLink() { return '/api/v1/fees/reports/student-ledger/export/?student=' + this.studentId; }
  challan(id: string) { return '/api/v1/fees/invoices/' + id + '/challan/'; }
  receipt(id: string) { return '/api/v1/fees/payments/' + id + '/receipt/'; }
}
