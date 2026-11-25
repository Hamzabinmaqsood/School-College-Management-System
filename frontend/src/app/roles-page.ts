import { Component, HostListener, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { AdminApi, Page, RequestState } from './admin';
import { AuthService } from './auth';

export interface Role {
  id: string; name: string; description: string; active: boolean; system: boolean; key: string | null;
  member_count: number; members?: {id: string; username: string}[];
}
interface CatalogRow {module: string; actions: Record<string, string>; reserved: boolean}
interface Grants {permissions: string[]; editable: boolean}
export const actions = ['view', 'details', 'add', 'update', 'delete', 'approve', 'verify', 'suspend', 'export', 'print', 'manage', 'submit', 'publish'];

export function changeGrants(previous: Set<string>, keys: string[], checked: boolean) {
  const result = new Set(previous);
  for (const key of keys) {
    if (checked) result.add(key);
    else result.delete(key);
  }
  return result;
}

@Component({
  imports: [FormsModule, MatButtonModule],
  templateUrl: './roles-page.html',
})
export class RolesPage {
  readonly auth = inject(AuthService);
  private readonly api = inject(AdminApi);
  readonly state = new RequestState();
  readonly page = signal<Page<Role> | null>(null);
  readonly selected = signal<Role | null>(null);
  readonly editor = signal<'new' | 'edit' | null>(null);
  readonly rows = signal<CatalogRow[]>([]);
  readonly draft = signal(new Set<string>());
  readonly editable = signal(false);
  readonly actions = actions;
  private saved = new Set<string>();
  search = '';
  status = '';
  type = '';
  moduleSearch = '';
  offset = 0;
  form = {name: '', description: '', active: true};

  constructor() { void this.load(); }

  load(offset = 0) {
    this.offset = offset;
    return this.state.run(async () => {
      this.page.set(await this.api.read<Page<Role>>('roles/', {
        search: this.search, active: this.status, system: this.type, offset,
      }));
    });
  }

  dirty() {
    const draft = this.draft();
    return draft.size !== this.saved.size || [...draft].some(key => !this.saved.has(key));
  }

  @HostListener('window:beforeunload', ['$event'])
  beforeUnload(event: BeforeUnloadEvent) {
    if (this.dirty()) event.preventDefault();
  }

  async leaveMatrix() {
    return !this.auth.user() || !this.dirty() || !!(await this.api.confirm('Discard unsaved permission changes?'));
  }

  async inspect(role: Role) {
    if (!await this.leaveMatrix()) return;
    await this.state.run(async () => {
      const path = 'roles/' + role.id + '/';
      const [detail, catalog, grants] = await Promise.all([
        this.api.read<Role>(path), this.api.read<CatalogRow[]>('permissions/'), this.api.read<Grants>(path + 'permissions/'),
      ]);
      this.selected.set(detail);
      this.rows.set(catalog);
      this.setGrants(grants);
      this.editor.set(null);
    });
  }

  private setGrants(grants: Grants) {
    this.saved = new Set(grants.permissions);
    this.draft.set(new Set(this.saved));
    this.editable.set(grants.editable);
  }

  edit(role?: Role) {
    this.form = {name: role?.name ?? '', description: role?.description ?? '', active: role?.active ?? true};
    this.editor.set(role ? 'edit' : 'new');
  }

  async saveRole() {
    const selected = this.editor() === 'edit' ? this.selected() : null;
    if (selected && selected.active !== this.form.active &&
        !await this.api.confirm('Change the active status of this role and its permissions?')) return;
    if (await this.state.run(async () => {
      const record = await this.api.write<Role>(selected ? 'PATCH' : 'POST',
        selected ? 'roles/' + selected.id + '/' : 'roles/', this.form);
      if (selected) this.selected.set({...selected, ...record});
      this.editor.set(null);
    }, 'Role saved.')) await this.load(this.offset);
  }

  assignable(key: string | undefined): key is string {
    return !!key && this.editable() && this.auth.has(key);
  }

  set(keys: (string | undefined)[], checked: boolean) {
    this.draft.update(current => changeGrants(current, keys.filter(key => this.assignable(key)) as string[], checked));
  }

  keys(row: CatalogRow) { return Object.values(row.actions); }

  visibleRows() {
    return this.rows().filter(row => row.module.toLowerCase().includes(this.moduleSearch.toLowerCase()));
  }

  async saveMatrix() {
    const role = this.selected();
    if (!role || !this.editable() || !await this.api.confirm('Apply these permissions to all members of this role?')) return;
    await this.state.run(async () => {
      this.setGrants(await this.api.write<Grants>('PUT', 'roles/' + role.id + '/permissions/', {
        permissions: [...this.draft()],
      }));
      await this.auth.refresh();
    }, 'Permissions saved.');
  }

  resetMatrix() { this.draft.set(new Set(this.saved)); }

  async remove(role: Role) {
    if (!await this.api.confirm('Delete the unassigned role “' + role.name + '”?')) return;
    if (await this.state.run(async () => {
      await this.api.write('DELETE', 'roles/' + role.id + '/');
      this.selected.set(null);
      this.setGrants({permissions: [], editable: false});
    }, 'Role deleted.')) await this.load();
  }
}
