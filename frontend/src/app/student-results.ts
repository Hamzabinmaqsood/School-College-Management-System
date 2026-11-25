import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AuthService } from './auth';

interface Result {
  id: string; exam: string; session: string; active: boolean; revision: number;
  percentage: string; grade: string; status: string; rank: number | null;
  subjects: {subject: string; obtained: string | null; maximum: string | null; grade: string | null; status: string}[];
}

@Component({
  selector:'app-student-results',
  imports:[FormsModule, MatButtonModule],
  template: `
    <section class="panel">
      <h2>Examination results</h2>
      @if (state.loading()) { <p role="status">Loading published results…</p> }
      @if (state.error()) { <p role="alert">{{ state.error() }}</p> }
      @if (records().length) {
        <div class="attendance-fields">
          <label>Session <select [(ngModel)]="session"><option value="">All sessions</option>
            @for (name of distinct('session'); track name) { <option>{{ name }}</option> }</select></label>
          <label>Exam <select [(ngModel)]="exam"><option value="">All exams</option>
            @for (name of distinct('exam'); track name) { <option>{{ name }}</option> }</select></label>
        </div>
      }
      <div class="attendance-rows">
        @for (row of filtered(); track row.id) {
          <article>
            <h3>{{ row.exam }}</h3><p>{{ row.session }} · Revision {{ row.revision }}
              · {{ row.active ? 'Published' : 'Withdrawn' }}</p>
            <p>{{ row.percentage }}% · {{ row.grade }} · {{ row.status }}</p>
            <details><summary>Subject results</summary>
              @for (subject of row.subjects; track $index) {
                <p>{{ subject.subject }} · {{ subject.obtained ?? '—' }}/{{ subject.maximum ?? '—' }}
                  · {{ subject.grade ?? subject.status }}</p>
              }
            </details>
            @if (auth.has('accounts.print_exam_results')) {
              <a [href]="'/api/v1/examinations/results/' + row.id + '/report-card/'" target="_blank" rel="noopener">Print report card</a>
            }
          </article>
        } @empty { @if (!state.loading()) { <p>No published results match these filters.</p> } }
      </div>
    </section>`,
})
export class StudentResults implements OnInit {
  @Input({required:true}) studentId = '';
  readonly auth = inject(AuthService);
  readonly api = inject(AdminApi);
  readonly state = new RequestState();
  readonly records = signal<Result[]>([]);
  session = '';
  exam = '';

  ngOnInit() {
    void this.state.run(async () => {
      const results: Result[] = [];
      let offset = 0;
      for (;;) {
        const page = await this.api.read<Page<Result>>('examinations/results/student/' + this.studentId + '/',
          {limit:100, offset});
        results.push(...page.results);
        if (!page.next || !page.results.length) break;
        offset += page.results.length;
      }
      this.records.set(results);
    });
  }

  distinct(key: 'session'|'exam') { return [...new Set(this.records().map(row => row[key]))]; }
  filtered() { return this.records().filter(row => (!this.session || row.session === this.session) &&
    (!this.exam || row.exam === this.exam)); }
}
