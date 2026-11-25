import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, firstValueFrom, switchMap, throwError } from 'rxjs';

export interface Brand {
  id: string;
  name: string;
  code: string;
  language: 'en' | 'ur';
  currency: string;
  timezone: string;
  logo_url: string | null;
}

export interface Identity {
  id: string;
  username: string;
  full_name: string;
  roles: {id: string; name: string}[];
  permissions: string[];
  password_change_required: boolean;
  institution: Brand | null;
}

interface Csrf {csrf_token: string; institution: Brand | null}

export function allowed(user: Identity | null, permission: string) {
  return !!user && (user.permissions.includes(permission) ||
    (permission === 'accounts.view_subscription' && user.permissions.includes('accounts.manage_subscription')));
}

export function destination(user: Identity | null, path: string, permission?: string): string | null {
  if (!user) return path === '/login' ? null : '/login';
  if (user.password_change_required) return path === '/change-password' ? null : '/change-password';
  if (!user.institution && allowed(user, 'accounts.change_institution')) {
    return path === '/setup/institution' ? null : '/setup/institution';
  }
  if (path === '/login') return '/dashboard';
  if (permission && !allowed(user, permission)) return '/access-denied';
  return null;
}

@Injectable({providedIn: 'root'})
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly user = signal<Identity | null>(null);
  readonly branding = signal<Brand | null>(null);
  readonly expired = signal(false);
  private pending?: Promise<Identity | null>;

  has(permission: string) { return allowed(this.user(), permission); }

  setUser(user: Identity | null) {
    this.user.set(user);
    if (user) this.branding.set(user.institution);
    document.documentElement.lang = this.branding()?.language ?? 'en';
    document.documentElement.dir = this.branding()?.language === 'ur' ? 'rtl' : 'ltr';
  }

  refresh() {
    this.pending ??= firstValueFrom(this.http.get<Identity>('/api/v1/auth/me/'))
      .then(user => { this.setUser(user); return user; })
      .catch((error: unknown) => {
        if (error instanceof HttpErrorResponse && error.status === 401) {
          this.setUser(null);
          return null;
        }
        throw error;
      }).finally(() => { this.pending = undefined; });
    return this.pending;
  }

  loadBranding() {
    return firstValueFrom(this.http.get<Csrf>('/api/v1/auth/csrf/')).then(data => this.branding.set(data.institution));
  }

  async login(username: string, password: string) {
    const user = await firstValueFrom(this.http.post<Identity>('/api/v1/auth/login/', {username, password}));
    this.expired.set(false);
    this.setUser(user);
    return user;
  }

  async changePassword(current_password: string, new_password: string) {
    const user = await firstValueFrom(this.http.post<Identity>('/api/v1/auth/change-password/', {
      current_password, new_password,
    }));
    this.setUser(user);
    return user;
  }

  async logout() {
    await firstValueFrom(this.http.post('/api/v1/auth/logout/', {}));
    this.setUser(null);
  }
}

export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith('/api/v1/')) return next(request);
  const auth = inject(AuthService);
  const router = inject(Router);
  const http = inject(HttpClient);
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);
  const response = unsafe
    ? http.get<Csrf>('/api/v1/auth/csrf/').pipe(switchMap(data =>
      next(request.clone({setHeaders: {'X-CSRFToken': data.csrf_token}}))))
    : next(request);
  return response.pipe(catchError((error: HttpErrorResponse) => {
    if (error.status === 401 && auth.user() && request.url !== '/api/v1/auth/login/') {
      auth.expired.set(true);
      auth.setUser(null);
      void router.navigateByUrl('/login');
    } else if (error.status === 403 && auth.user()) {
      void auth.refresh().catch(() => undefined);
    }
    return throwError(() => error);
  }));
};

export const accountGuard: CanActivateFn = async (route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const path = state.url.split(/[?#]/, 1)[0] ?? '/';
  try {
    const user = await auth.refresh();
    const redirect = destination(user, path, route.data['permission'] as string | undefined);
    const any = route.data["anyPermission"] as string[] | undefined;
    if (!redirect && any && !any.some(permission => allowed(user, permission))) return router.parseUrl("/access-denied");
    return redirect ? router.parseUrl(redirect) : true;
  } catch {
    return path === '/login' ? true : router.parseUrl('/login');
  }
};

export function errorMessage(error: unknown) {
  if (!(error instanceof HttpErrorResponse)) return 'The operation could not be completed.';
  if (!error.status || error.status >= 500) return 'Backend unavailable. Try again when the service is online.';
  const body = error.error as {message?: string; details?: Record<string, unknown>} | null;
  const fields = body?.details;
  const messages = (value: unknown): string[] => {
    if (typeof value === 'string') return [value];
    if (Array.isArray(value)) return value.flatMap(messages);
    if (value && typeof value === 'object') return Object.values(value).flatMap(messages);
    return [];
  };
  const validation = messages(fields);
  if (validation.length) return validation.join(' ');
  return body?.message ?? 'The operation could not be completed.';
}
