import { Component, DestroyRef, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { ActivatedRoute, Router } from '@angular/router';
import { AdminApi, RequestState } from './admin';
import { AuthService, Brand } from './auth';

const defaults = {
  code: '', name: '', institution_type: 'school', registration_number: '', principal: '',
  email: '', phone: '', address: '', city: '', province: '', country: 'Pakistan',
  currency: 'PKR', timezone: 'Asia/Karachi', language: 'en',
};

@Component({
  imports: [FormsModule, MatButtonModule],
  templateUrl: './institution-page.html',
})
export class InstitutionPage {
  readonly auth = inject(AuthService);
  private readonly api = inject(AdminApi);
  private readonly router = inject(Router);
  readonly state = new RequestState();
  readonly setup = inject(ActivatedRoute).snapshot.data['setup'] === true;
  readonly data = {...defaults};
  readonly preview = signal<string | null>(this.auth.branding()?.logo_url ?? null);
  private logo?: File;
  private objectUrl?: string;
  readonly fields = [
    ['code', 'Institution code'], ['name', 'Institution name'], ['registration_number', 'Registration number'],
    ['principal', 'Principal or director'], ['email', 'Email'], ['phone', 'Phone'], ['address', 'Address'],
    ['city', 'City'], ['province', 'Province'], ['country', 'Country'], ['currency', 'Currency'],
    ['timezone', 'Timezone'],
  ] as const;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.revokePreview());
    void this.state.run(async () => {
      const existing = await this.api.read<(typeof defaults & Brand) | null>('institution/');
      if (existing) Object.assign(this.data, existing);
    });
  }
  private revokePreview() {
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
  }
  choose(event: Event) {
    this.revokePreview();
    this.logo = (event.target as HTMLInputElement).files?.[0];
    this.objectUrl = this.logo ? URL.createObjectURL(this.logo) : undefined;
    this.preview.set(this.objectUrl ?? this.auth.branding()?.logo_url ?? null);
  }
  async save() {
    if (!this.auth.has('accounts.change_institution')) return;
    await this.state.run(async () => {
      const payload = new FormData();
      for (const key of Object.keys(defaults) as (keyof typeof defaults)[]) payload.append(key, this.data[key]);
      if (this.logo) payload.append('logo', this.logo);
      await this.api.write('PATCH', 'institution/', payload);
      await this.auth.refresh();
      if (this.setup) await this.router.navigateByUrl('/dashboard');
    }, 'Institution details saved.');
  }
  async leave() {
    await this.state.run(async () => {
      await this.auth.logout();
      await this.router.navigateByUrl('/login');
    });
  }
}
