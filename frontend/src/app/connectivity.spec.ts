import { describe, expect, it, vi } from 'vitest';
import { checkConnectivity, Connectivity } from './connectivity';

describe('dashboard connectivity', () => {
  it('checks both public endpoints', async () => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({status: 'ok'}))
      .mockResolvedValueOnce(Response.json({status: 'ready', database: 'connected'}));
    await expect(checkConnectivity(request)).resolves.toEqual({
      backend: 'connected', database: 'connected',
    });
    expect(request.mock.calls.map(([url]) => url)).toEqual(['/api/v1/health/', '/api/v1/ready/']);
  });

  it('shows a loading state while refreshing', async () => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({status: 'ok'}))
      .mockResolvedValueOnce(Response.json({status: 'ready', database: 'connected'}));
    request
      .mockResolvedValueOnce(Response.json({status: 'ok'}))
      .mockResolvedValueOnce(Response.json({status: 'ready', database: 'connected'}));
    vi.stubGlobal('fetch', request);
    try {
      const connectivity = new Connectivity();
      await connectivity.refresh();
      const refresh = connectivity.refresh();
      expect(connectivity.status()).toEqual({backend: 'checking', database: 'checking'});
      await refresh;
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('keeps backend health separate from a readiness 503', async () => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({status: 'ok'}))
      .mockResolvedValueOnce(Response.json({status: 'not_ready'}, {status: 503}));
    await expect(checkConnectivity(request)).resolves.toEqual({
      backend: 'connected', database: 'unavailable',
    });
  });

  it('handles network errors and invalid payloads', async () => {
    const request = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new Error('Offline'))
      .mockResolvedValueOnce(new Response('<html>'));
    await expect(checkConnectivity(request)).resolves.toEqual({
      backend: 'unavailable', database: 'unavailable',
    });
  });
});
