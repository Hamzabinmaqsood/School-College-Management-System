import { Injectable, signal } from '@angular/core';

export type ConnectionState = 'checking' | 'connected' | 'unavailable';
export type ConnectionStatus = {backend: ConnectionState; database: ConnectionState};

async function probe(path: string, matches: (body: unknown) => boolean, request: typeof fetch) {
  try {
    const response = await request(path, {signal: AbortSignal.timeout(5000), cache: 'no-store'});
    return response.ok && matches(await response.json());
  } catch {
    return false;
  }
}

export async function checkConnectivity(request = fetch): Promise<ConnectionStatus> {
  const [backend, database] = await Promise.all([
    probe('/api/v1/health/', body => !!body && typeof body === 'object' &&
      'status' in body && body.status === 'ok', request),
    probe('/api/v1/ready/', body => !!body && typeof body === 'object' &&
      'status' in body && body.status === 'ready' &&
      'database' in body && body.database === 'connected', request),
  ]);
  return {
    backend: backend ? 'connected' : 'unavailable',
    database: database ? 'connected' : 'unavailable',
  };
}

@Injectable({providedIn: 'root'})
export class Connectivity {
  readonly status = signal<ConnectionStatus>({backend: 'checking', database: 'checking'});

  private requestId = 0;

  async refresh() {
    const id = ++this.requestId;
    this.status.set({backend: 'checking', database: 'checking'});
    const latest = await checkConnectivity();
    if (id === this.requestId) this.status.set(latest);
  }
}
