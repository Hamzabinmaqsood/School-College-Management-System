import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminApi, Page, RequestState } from './admin';
import { AuthService } from './auth';
import {
  activationPayload, InstallationDetails, licenseLabel, LicenseStatus, licenseTone, renewalMessage,
  VerifiedLicense,
} from './license';

@Component({
  imports: [DatePipe, FormsModule, MatButtonModule, MatIconModule, RouterLink],
  templateUrl: './license-page.html',
})
export class LicensePage {
  readonly auth = inject(AuthService);
  private readonly api = inject(AdminApi);
  readonly activation = inject(ActivatedRoute).snapshot.data['activation'] === true;
  readonly installation = signal<InstallationDetails | null>(null);
  readonly status = signal<LicenseStatus | null>(null);
  readonly history = signal<Page<VerifiedLicense & {current: boolean}> | null>(null);
  readonly state = new RequestState();
  readonly formError = signal('');
  readonly label = licenseLabel;
  readonly tone = licenseTone;
  readonly reminder = renewalMessage;
  readonly duration: Record<string, string> = {'1m': '1 month', '3m': '3 months', '6m': '6 months', '12m': '12 months', custom: 'Custom term'};
  readonly file = signal<File | null>(null);
  pasted = '';
  offset = 0;

  constructor() {
    void this.state.run(async () => {
      this.status.set(await this.api.read<LicenseStatus>('license/status/'));
      this.installation.set(await this.api.read<InstallationDetails>('license/installation/'));
      if (!this.activation) await this.readHistory();
    });
  }

  choose(event: Event) {
    const input = event.target as HTMLInputElement;
    this.file.set(input.files?.[0] ?? null);
    this.formError.set('');
  }

  async copy() {
    const details = this.installation();
    if (!details) return;
    await this.state.run(async () => {
      await navigator.clipboard.writeText(details.installation_id);
    }, 'Installation ID copied.');
  }

  private async readHistory() {
    this.history.set(await this.api.read<Page<VerifiedLicense & {current: boolean}>>(
      'license/history/', {offset: this.offset},
    ));
  }

  loadHistory(offset: number) {
    this.offset = offset;
    return this.state.run(() => this.readHistory());
  }

  async submit(fileInput: HTMLInputElement) {
    this.formError.set('');
    this.state.success.set('');
    let payload: ReturnType<typeof activationPayload>;
    try {
      payload = activationPayload(this.file(), this.pasted);
    } catch (error) {
      this.formError.set(error instanceof Error ? error.message : 'Choose a license.');
      return;
    }
    if (!this.installation()?.can_activate || this.state.loading()) return;
    await this.state.run(async () => {
      const response = await this.api.write<LicenseStatus>('POST', 'license/activate/', payload);
      this.status.set(response);
      this.pasted = '';
      this.file.set(null);
      fileInput.value = '';
      this.state.success.set(response.duplicate ? 'This license is already recorded.' : 'License verified and activated.');
    });
  }
}
