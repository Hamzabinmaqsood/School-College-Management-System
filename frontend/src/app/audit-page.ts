import { DatePipe, JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';

interface Entry {id: string; actor: string | null; action: string; resource: string; resource_id: string;
  timestamp: string; request_id: string; metadata: Record<string, unknown>}

@Component({
  imports: [FormsModule, DatePipe, JsonPipe, MatButtonModule],
  templateUrl: './audit-page.html',
})
export class AuditPage {
  private readonly api = inject(AdminApi);
  readonly state = new RequestState();
  readonly page = signal<Page<Entry> | null>(null);
  readonly selected = signal<Entry | null>(null);
  fields = {search: '', action: '', user: '', from: '', to: ''};
  offset = 0;

  constructor() { void this.load(); }

  load(offset = 0) {
    this.offset = offset;
    return this.state.run(async () => {
      this.page.set(await this.api.read<Page<Entry>>('audit/', {...this.fields, offset}));
    });
  }

  async inspect(id: string) {
    await this.state.run(async () => {
      this.selected.set(await this.api.read<Entry>('audit/' + id + '/'));
    });
  }
}
