import { BreakpointObserver } from '@angular/cdk/layout';
import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatSidenavModule } from '@angular/material/sidenav';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs';
import { visibleNavigation } from './navigation';
import { AuthService, errorMessage } from './auth';

@Component({
  imports: [MatButtonModule, MatIconModule, MatMenuModule, MatSidenavModule, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './app.html',
})
export class AppShell {
  private readonly router = inject(Router);
  readonly auth = inject(AuthService);
  readonly sessionError = signal('');
  readonly navigation = computed(() => visibleNavigation(this.auth.user()?.permissions ?? []));
  readonly profile = computed(() => this.auth.user()?.full_name || this.auth.user()?.username || '');
  readonly compact = toSignal(inject(BreakpointObserver).observe('(max-width: 850px)').pipe(
    map(result => result.matches),
  ), {initialValue: false});
  readonly desktopOpen = signal(true);
  readonly mobileOpen = signal(false);
  readonly dark = signal(false);
  readonly opened = computed(() => this.compact() ? this.mobileOpen() : this.desktopOpen());
  readonly page = toSignal(this.router.events.pipe(
    filter(event => event instanceof NavigationEnd),
    startWith(null),
    map(() => this.router.routerState.snapshot.root.firstChild?.firstChild?.title ?? 'Dashboard'),
  ), {requireSync: true});

  @HostListener('window:focus')
  refreshSession() {
    void this.auth.refresh().catch(() => undefined);
  }

  async signOut() {
    try {
      await this.auth.logout();
      await this.router.navigateByUrl('/login');
    } catch (error) {
      this.sessionError.set(errorMessage(error));
    }
  }

  setNavigation(opened: boolean) {
    (this.compact() ? this.mobileOpen : this.desktopOpen).set(opened);
  }

  toggleTheme() {
    this.dark.update(value => !value);
    document.documentElement.dataset['theme'] = this.dark() ? 'dark' : 'light';
  }
}

@Component({selector: 'app-root', imports: [RouterOutlet], template: '<router-outlet />'})
export class App {}
