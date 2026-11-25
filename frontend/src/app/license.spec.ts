import '@angular/compiler';
import { describe, expect, it } from 'vitest';
import { destination } from './auth';
import { activationPayload, licenseLabel, licenseTone, renewalMessage } from './license';
import { visibleNavigation } from './navigation';

describe('licensing interface', () => {
  it('accepts a pasted code or upload independently', () => {
    expect(activationPayload(null, '  SMS1.test.code  ')).toEqual({token: 'SMS1.test.code'});
    const item = new File(['SMS1.test.code'], 'download.smslicense');
    expect((activationPayload(item, '') as FormData).get('file')).toEqual(item);
    expect(() => activationPayload(item, 'code')).toThrow('Choose');
    expect(() => activationPayload(null, '')).toThrow('Choose');
  });

  it('rejects an oversized upload', () => {
    const item = new File(['x'.repeat(16_387)], 'large.smslicense');
    expect(() => activationPayload(item, '')).toThrow('16 KB');
  });

  it('maps actual license states and deadlines to dashboard presentation', () => {
    expect(licenseLabel('ACTIVE')).toBe('Active');
    expect(licenseTone('INVALID_SIGNATURE')).toBe('red');
    expect(renewalMessage({status: 'EXPIRING_SOON', write_allowed: true, days_remaining: 7})).toContain('7 days');
    expect(renewalMessage({status: 'EXPIRED', write_allowed: false})).toContain('Renew');
    expect(renewalMessage({status: 'CLOCK_REVIEW_REQUIRED', write_allowed: false})).toContain('server’s UTC time');
    expect(renewalMessage({status: 'GRACE_PERIOD', write_allowed: false})).toContain('Existing records remain');
  });

  it('protects activation separately from read-only subscription access', () => {
    const institution = {id: 'school', name: 'School', code: 'school', language: 'en' as const,
      timezone: 'UTC', currency: 'PKR', logo_url: null};
    const reader = {id: 'reader', username: 'reader', full_name: '', roles: [], institution,
      permissions: ['accounts.view_subscription'], password_change_required: false};
    expect(destination(null, '/activation')).toBe('/login');
    expect(destination(reader, '/activation', 'accounts.manage_subscription')).toBe('/access-denied');
    expect(destination(reader, '/subscription', 'accounts.view_subscription')).toBeNull();
    expect(visibleNavigation(['accounts.manage_subscription']).flatMap(group => group.items.map(item => item.path)))
      .toContain('subscription');
  });
});
