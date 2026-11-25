import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AuthService } from './auth';
import type { Role } from './roles-page';

interface User {
  id: string; username: string; first_name: string; last_name: string; full_name: string;
  email: string; phone: string; active: boolean; last_login: string | null;
  roles: {id: string; name: string; active: boolean}[];
}
interface UserPage extends Page<User> {summary: {total: number; active: number; inactive: number}}
const blank = {username: '', first_name: '', last_name: '', email: '', phone: '', password: '', role_ids: [] as string[]};

@Component({
  imports: [DatePipe, FormsModule, MatButtonModule],
  templateUrl: './users-page.html',
})
export class UsersPage {
  readonly auth = inject(AuthService);
  private readonly api = inject(AdminApi);
  readonly state = new RequestState();
  readonly page = signal<UserPage | null>(null);
  readonly choices = signal<Role[]>([]);
  readonly selected = signal<User | null>(null);
  readonly permissions = signal<string[]>([]);
  readonly editor = signal<'new' | 'edit' | 'assign' | 'reset' | null>(null);
  readonly fields = [
    ['username', 'Username'], ['first_name', 'First name'], ['last_name', 'Last name'],
    ['email', 'Email'], ['phone', 'Phone'],
  ] as const;
  form = {...blank};
  search = '';
  role = '';
  active = '';
  offset = 0;

  constructor() { void this.initialize(); }

  async initialize() {
    await this.load();
    if (this.auth.has('auth.view_group')) {
      await this.state.run(async () => {
        const roles: Role[] = [];
        let offset = 0;
        for (;;) {
          const page = await this.api.read<Page<Role>>('roles/', {limit: 100, offset});
          roles.push(...page.results);
          if (!page.next || !page.results.length) break;
          offset += page.results.length;
        }
        this.choices.set(roles);
      });
    }
  }

  load(offset = 0) {
    this.offset = offset;
    return this.state.run(async () => {
      this.page.set(await this.api.read<UserPage>('users/', {
        search: this.search, role: this.role, active: this.active, offset,
      }));
    });
  }

  async inspect(user: User) {
    await this.state.run(async () => {
      const path = 'users/' + user.id + '/';
      const [record, grants] = await Promise.all([
        this.api.read<User>(path), this.api.read<{permissions: string[]}>(path + 'permissions/'),
      ]);
      this.selected.set(record);
      this.permissions.set(grants.permissions);
    });
  }

  edit(mode: 'new' | 'edit' | 'assign' | 'reset', user?: User) {
    this.selected.set(user ?? null);
    this.form = {...blank, ...user, role_ids: user?.roles.filter(role => role.active).map(role => role.id) ?? []};
    this.editor.set(mode);
  }

  async save() {
    const user = this.selected();
    const mode = this.editor();
    if (!mode) return;
    if (['assign', 'reset'].includes(mode) &&
        !await this.api.confirm(mode === 'reset' ? 'Reset this user’s password and end their current sessions?' : 'Replace this user’s role assignments?')) return;
    const path = 'users/' + (user ? user.id + '/' : '');
    const profile = Object.fromEntries(this.fields.map(([key]) => [key, this.form[key]]));
    const saved = await this.state.run(async () => {
      if (mode === 'new') {
        await this.api.write('POST', path, {...profile, password: this.form.password,
          ...(this.auth.has('accounts.assign_roles') ? {role_ids: this.form.role_ids} : {})});
      } else if (mode === 'reset') {
        await this.api.write('POST', path + 'reset-password/', {password: this.form.password});
      } else {
        await this.api.write('PATCH', path, mode === 'assign' ? {role_ids: this.form.role_ids} : profile);
      }
      this.editor.set(null);
      this.selected.set(null);
    }, 'User saved.');
    this.form.password = '';
    if (saved) await this.load(this.offset);
  }

  async status(user: User) {
    const action = user.active ? 'deactivate' : 'activate';
    if (!await this.api.confirm('Confirm account status change for ' + user.username + '?')) return;
    if (await this.state.run(async () => {
      await this.api.write('POST', 'users/' + user.id + '/' + action + '/', {});
      this.selected.set(null);
    }, 'Account status updated.')) await this.load(this.offset);
  }
}
