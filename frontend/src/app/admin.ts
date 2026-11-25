import { HttpClient } from '@angular/common/http';
import { Component, Injectable, inject, signal } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { firstValueFrom } from 'rxjs';
import { errorMessage } from './auth';

export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }

@Injectable({providedIn: 'root'})
export class AdminApi {
  private readonly http = inject(HttpClient);
  private readonly dialog = inject(MatDialog);

  read<T>(path: string, params: Record<string, string | number> = {}) {
    return firstValueFrom(this.http.get<T>('/api/v1/' + path, {params}));
  }
  write<T>(method: string, path: string, body?: unknown) {
    return firstValueFrom(this.http.request<T>(method, '/api/v1/' + path, {body}));
  }
  confirm(message: string) {
    return firstValueFrom(this.dialog.open<ConfirmDialog, string, boolean>(ConfirmDialog, {data: message, enterAnimationDuration: 0, exitAnimationDuration: 0}).afterClosed());
  }
}

@Component({
  imports: [MatDialogModule, MatButtonModule],
  template: '<h2 mat-dialog-title>Confirm change</h2><mat-dialog-content style="white-space: pre-line">{{ message }}</mat-dialog-content>' +
    '<mat-dialog-actions align="end"><button mat-button type="button" (click)="dialog.close(false)" >Cancel</button>' +
    '<button mat-flat-button type="button" (click)="dialog.close(true)" >Confirm</button></mat-dialog-actions>',
})
export class ConfirmDialog {
  readonly message = inject<string>(MAT_DIALOG_DATA);
  readonly dialog = inject<MatDialogRef<ConfirmDialog, boolean>>(MatDialogRef);
}

export class RequestState {
  readonly loading = signal(false);
  readonly error = signal('');
  readonly success = signal('');

  async run(task: () => Promise<void>, success = '') {
    this.error.set('');
    this.loading.set(true);
    try {
      await task();
      if (success) this.success.set(success);
      return true;
    } catch (error) {
      this.error.set(errorMessage(error));
      return false;
    } finally {
      this.loading.set(false);
    }
  }
}
