export interface VerifiedLicense {
  license_id: string;
  institution_name: string;
  installation_id: string;
  edition: string;
  valid_from: string;
  expires_at: string;
  activated_at: string;
  duration: string;
  features: string[];
}

export interface LicenseStatus {
  status: string;
  days_remaining?: number;
  grace_deadline?: string | null;
  reminder_days?: number | null;
  write_allowed: boolean;
  available_features?: string[];
  license?: VerifiedLicense | null;
  duplicate?: boolean;
}

export interface InstallationDetails {
  institution_id: string;
  institution_name: string;
  installation_id: string;
  can_activate: boolean;
}

const labels: Record<string, string> = {
  NOT_ACTIVATED: 'Not activated', ACTIVE: 'Active', EXPIRING_SOON: 'Expiring soon',
  GRACE_PERIOD: 'Grace period', EXPIRED: 'Expired', INVALID_SIGNATURE: 'Invalid signature',
  INVALID_LICENSE: 'Invalid license', INSTALLATION_MISMATCH: 'Installation mismatch',
  CLOCK_REVIEW_REQUIRED: 'Server clock review required', NOT_YET_VALID: 'Not yet valid',
};

export function licenseLabel(status: string) { return labels[status] ?? 'License unavailable'; }

export function licenseTone(status: string) {
  return status === 'ACTIVE' ? 'green' : ['EXPIRING_SOON', 'GRACE_PERIOD', 'NOT_ACTIVATED'].includes(status)
    ? 'orange' : 'red';
}

export function renewalMessage(status: LicenseStatus) {
  switch (status.status) {
    case 'EXPIRING_SOON':
      return (status.days_remaining ?? 0) <= 1 ? 'Renew within the final day.' :
        'Renew within ' + status.days_remaining + ' days.';
    case 'EXPIRED': return 'Renew to restore licensed business writes.';
    case 'GRACE_PERIOD': return status.write_allowed
      ? 'Renew before the grace deadline to avoid write restrictions.'
      : 'Existing records remain available during the grace period.';
    case 'CLOCK_REVIEW_REQUIRED': return 'Check the server’s UTC time. Contact the vendor if the clock was moved forward by mistake.';
    case 'NOT_ACTIVATED': return 'Import a vendor-issued license to enable licensed business writes.';
    case 'ACTIVE': return '';
    default: return 'Review the subscription and import a valid vendor-issued license.';
  }
}

export function activationPayload(file: File | null, pasted: string) {
  const token = pasted.trim();
  if (file && token) throw new Error('Choose a license file or paste an activation code.');
  if (!file && !token) throw new Error('Choose a license file or paste an activation code.');
  if (file && file.size > 16386 || token.length > 16384) throw new Error('License files and codes are limited to 16 KB.');
  if (!file) return {token};
  const payload = new FormData();
  payload.append('file', file);
  return payload;
}
