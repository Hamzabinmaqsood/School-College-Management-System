import { Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService, destination, errorMessage } from './auth';

@Component({
  imports: [ReactiveFormsModule, MatButtonModule, MatIconModule],
  templateUrl: './auth-page.html',
})
export class AuthPage {
  readonly auth = inject(AuthService);
  readonly change = inject(ActivatedRoute).snapshot.data['change'] === true;
  private readonly router = inject(Router);
  readonly visible = signal(false);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly form = new FormGroup({
    username: new FormControl('', {nonNullable: true, validators: Validators.required}),
    password: new FormControl('', {nonNullable: true, validators: Validators.required}),
    newPassword: new FormControl('', {nonNullable: true, validators: Validators.required}),
  });

  constructor() {
    this.form.controls[this.change ? 'username' : 'newPassword'].disable();
    if (!this.change) void this.auth.loadBranding().catch(error => this.error.set(errorMessage(error)));
  }

  async submit() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.loading()) return;
    this.error.set('');
    this.loading.set(true);
    const {username, password, newPassword} = this.form.getRawValue();
    try {
      const user = this.change ? await this.auth.changePassword(password, newPassword)
        : await this.auth.login(username, password);
      await this.router.navigateByUrl(destination(user, '/dashboard') ?? '/dashboard');
    } catch (error) {
      this.error.set(errorMessage(error));
    } finally {
      this.loading.set(false);
      this.form.controls.password.reset();
      this.form.controls.newPassword.reset();
    }
  }

  async leave() {
    try {
      await this.auth.logout();
      await this.router.navigateByUrl('/login');
    } catch (error) {
      this.error.set(errorMessage(error));
    }
  }
}
