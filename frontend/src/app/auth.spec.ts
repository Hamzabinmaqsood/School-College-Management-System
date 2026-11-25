import '@angular/compiler';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injector, runInInjectionContext } from '@angular/core';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { of, throwError } from 'rxjs';
import { AuthService, destination, errorMessage, Identity } from './auth';
import { visibleNavigation } from './navigation';
import { changeGrants } from './roles-page';

const user: Identity = {
  id: 'test', username: 'operator', full_name: 'Test Operator', roles: [],
  permissions: ['accounts.view_dashboard'], password_change_required: false,
  institution: {id: 'institution', name: 'Test School', code: 'test', language: 'en',
    currency: 'PKR', timezone: 'Asia/Karachi', logo_url: null},
};

describe('management access', () => {
  it('protects direct URLs and distinguishes sign-in from permission denial', () => {
    expect(destination(null, '/users')).toBe('/login');
    expect(destination(user, '/users', 'accounts.view_user')).toBe('/access-denied');
    expect(destination(user, '/dashboard', 'accounts.view_dashboard')).toBeNull();
  });
  it('requires password changes before the institution wizard', () => {
    const unconfigured = {...user, institution: null, permissions: ['accounts.change_institution']};
    expect(destination({...unconfigured, password_change_required: true}, '/dashboard')).toBe('/change-password');
    expect(destination(unconfigured, '/dashboard')).toBe('/setup/institution');
    expect(destination({...unconfigured, permissions: []}, '/dashboard')).toBeNull();
  });
  it('updates visible navigation when assigned grants change', () => {
    const paths = (permissions: string[]) => visibleNavigation(permissions).flatMap(group => group.items.map(item => item.path));
    expect(paths(['accounts.view_dashboard', 'accounts.view_students'])).toEqual(['dashboard', 'students']);
    expect(paths(['accounts.view_dashboard'])).toEqual(['dashboard']);
  });
  it('shows timetable navigation for institution or own-schedule access', () => {
    const timetable = (grants: string[]) => visibleNavigation(grants)
      .some(group => group.items.some(item => item.path === 'timetable'));
    expect(timetable(['accounts.view_timetable'])).toBe(true);
    expect(timetable(['accounts.view_own_timetable'])).toBe(true);
    expect(timetable(['accounts.view_staff'])).toBe(false);
  });

  it('updates a set of permission matrix cells without mutating saved state', () => {
    const saved = new Set(['accounts.view_user']);
    const selection = changeGrants(saved, ['accounts.change_user'], true);
    expect(selection.has('accounts.change_user')).toBe(true);
    expect(changeGrants(selection, [...saved], false)).toEqual(new Set(['accounts.change_user']));
    expect(saved).toEqual(new Set(['accounts.view_user']));
  });
  it('shows safe invalid-credentials and offline feedback', () => {
    expect(errorMessage(new HttpErrorResponse({status: 401, error: {message: 'Invalid credentials'}}))).toBe('Invalid credentials');
    expect(errorMessage(new HttpErrorResponse({status: 503}))).toMatch(/Backend unavailable/);
  });
});

describe('current account session', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('loads identity in memory and clears it when Django expires the session', async () => {
    vi.stubGlobal('document', {documentElement: {}});
    const get = vi.fn().mockReturnValueOnce(of(user))
      .mockReturnValueOnce(throwError(() => new HttpErrorResponse({status: 401})));
    const injector = Injector.create({providers: [{provide: HttpClient, useValue: {get}}]});
    const auth = runInInjectionContext(injector, () => new AuthService());
    await expect(auth.refresh()).resolves.toEqual(user);
    expect(auth.user()?.username).toBe('operator');
    await expect(auth.refresh()).resolves.toBeNull();
    expect(auth.user()).toBeNull();
  });
});
