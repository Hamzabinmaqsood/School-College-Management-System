#!/usr/bin/env bash
# Noninteractive backup and recovery probe. The source is read-only.
set -euo pipefail
umask 077
fail() { printf '%s\n' "$*" >&2; exit 1; }

root="$(cd "$(dirname "$0")/.." && pwd -P)"
mode="${1:---status}"
[[ "$mode" == --status || "$mode" == --verify ]] || fail 'Use --status or --verify.'
for variable in SMS_BACKUP_DIR SMS_BACKUP_RECIPIENT SMS_BACKUP_GNUPGHOME SMS_BACKUP_SOURCE_SERVICE SMS_BACKUP_EXPECTED_DB SMS_BACKUP_EXPECTED_PORT SMS_BACKUP_RETENTION_DAYS; do
    [[ -n "${!variable:-}" ]] || fail "Backup blocked. Configure $variable outside the repository."
done
[[ "$SMS_BACKUP_RECIPIENT" =~ ^[0-9A-Fa-f]{40}$ ]] || fail 'Use a full GPG recipient fingerprint.'
[[ "$SMS_BACKUP_RETENTION_DAYS" =~ ^[1-9][0-9]{0,3}$ ]] || fail 'Set a positive retention window in days.'
[[ "$SMS_BACKUP_SOURCE_SERVICE" =~ ^[a-zA-Z0-9_.-]+$ ]] || fail 'Use a named PostgreSQL service.'
[[ "$SMS_BACKUP_EXPECTED_PORT" =~ ^[0-9]{1,5}$ ]] || fail 'Set the expected PostgreSQL TCP port.'
destination="$(realpath -e -- "$SMS_BACKUP_DIR")"
keyring="$(realpath -e -- "$SMS_BACKUP_GNUPGHOME")"
for path in "$destination" "$keyring"; do
    [[ -d "$path" && "$path" != "$root" && "$path" != "$root/"* ]] || fail 'Use private directories outside the repository.'
    [[ "$(stat -c '%a:%u' "$path")" == "700:$(id -u)" ]] || fail 'Backup and keyring directories must have mode 0700 and belong to the operator.'
done
export GNUPGHOME="$keyring"
gpg --batch --no-auto-check-trustdb --list-secret-keys -- "$SMS_BACKUP_RECIPIENT" >/dev/null 2>&1 ||
    fail 'The configured recipient has no locally usable recovery key.'
pg="$(pg_config --bindir)"
source="service=$SMS_BACKUP_SOURCE_SERVICE"
identity="$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -d "$source" -c "SELECT current_database() || '|' || current_setting('port')")"
[[ "$identity" == "$SMS_BACKUP_EXPECTED_DB|$SMS_BACKUP_EXPECTED_PORT" ]] || fail 'Backup source identity differs from the reviewed configuration.'
eligible="$(find "$destination" -maxdepth 1 -type f -name 'school-*.dump.gpg' -mtime "+$SMS_BACKUP_RETENTION_DAYS" -printf '.' | wc -c)"
printf 'Source identity verified. Archives past the retention window: %s.\n' "$eligible"
[[ "$mode" == --verify ]] || exit 0

probe="$(mktemp -d /tmp/sms-recovery.XXXXXXXX)"
archive=
checksum=
cleanup() {
    "$pg/pg_ctl" -D "$probe/data" -m fast -w stop >/dev/null 2>&1 || true
    [[ -z "$archive" ]] || rm -f -- "$archive"
    [[ -z "$checksum" ]] || rm -f -- "$checksum"
    rm -rf -- "$probe"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
archive="$(mktemp "$destination/.backup.XXXXXXXX")"
checksum="$(mktemp "$destination/.checksum.XXXXXXXX")"
"$pg/initdb" -D "$probe/data" -A trust -U "$USER" >/dev/null
"$pg/pg_ctl" -D "$probe/data" -l "$probe/postgres.log" -o "-c listen_addresses='' -k $probe -p 55485" -w start >/dev/null
restore=(-h "$probe" -p 55485 -U "$USER")
"$pg/createdb" "${restore[@]}" sms_backup_verification
actual="$("$pg/psql" "${restore[@]}" -XAt -d sms_backup_verification -c "SELECT current_database() || '|' || current_setting('data_directory') || '|' || (inet_server_addr() IS NULL)")"
[[ "$actual" == "sms_backup_verification|$probe/data|true" ]] || fail 'Restore target did not identify itself as the private cluster.'

readback='SELECT count(*) FROM accounts_institution; SELECT count(*) FROM students_student; SELECT count(*) FROM attendance_attendancesession; SELECT count(*) FROM hr_payrollentry; SELECT app || chr(58) || name FROM django_migrations ORDER BY app,name;'
"$pg/psql" -XAt -v ON_ERROR_STOP=1 -d "$source" -c "$readback" >"$probe/before"
"$pg/pg_dump" --format=custom --dbname="$source" |
    gpg --batch --yes --trust-model always --encrypt --recipient "$SMS_BACKUP_RECIPIENT" --output "$archive"
gpg --batch --decrypt "$archive" |
    "$pg/pg_restore" "${restore[@]}" --exit-on-error --no-owner --no-privileges --dbname=sms_backup_verification
"$pg/psql" "${restore[@]}" -XAt -v ON_ERROR_STOP=1 -d sms_backup_verification -c "$readback" >"$probe/restored"
"$pg/psql" -XAt -v ON_ERROR_STOP=1 -d "$source" -c "$readback" >"$probe/after"
cmp -s "$probe/before" "$probe/after" || fail 'Source counts or migration records changed during verification. Retry in a quiet window.'
cmp -s "$probe/before" "$probe/restored" || fail 'Restored counts or migration records differ.'
final="$destination/school-$(date -u +%Y%m%dT%H%M%SZ)-${archive##*.}.dump.gpg"
digest="$(sha256sum <"$archive")"
printf '%s  %s\n' "${digest%% *}" "${final##*/}" >"$checksum"
ln -- "$archive" "$final"
if ! ln -- "$checksum" "$final.sha256"; then
    rm -f -- "$final"
    fail 'Could not publish the archive checksum.'
fi
printf 'Encrypted archive restored and representative counts and migration records matched.\n'
