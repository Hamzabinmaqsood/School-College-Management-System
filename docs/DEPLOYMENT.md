# Deployment Strategy

## 1. Standalone Windows

- PostgreSQL as a local service;
- Django under Waitress or a packaged Windows service;
- Angular static build served locally or by the Django static server;
- TLS for browser-to-server where practical;
- application data and backups on a separate, monitored drive;
- Windows Firewall local-only database rules.

The Python application and PostgreSQL service must run under dedicated low-privilege accounts.

## 2. LAN server

One Windows/Linux server is authoritative. Workstations connect to it through a fixed private hostname/address. PostgreSQL listens only on the LAN interface and loopback, with strong database passwords and firewall allowlists. The application binds to a private LAN address.

## 3. Linux future deployment

Use systemd services, Ubuntu PostgreSQL, a reverse proxy such as Caddy or nginx, local firewall rules, and an offline systemd deployment package. Containerization is optional and not required for initial deployments.

## 4. Packaging

Deployment packages are versioned and include:

- signed release manifest;
- frontend build;
- backend wheel/source package;
- migration instructions;
- PostgreSQL configuration templates;
- backup script;
- restore script;
- Windows service configuration;
- Linux systemd/Caddy/nginx templates.

## 5. Installation flow

1. validate OS, CPU, RAM, disk, and required ports;
2. create dedicated service account;
3. install PostgreSQL and configure private binding;
4. create database and least-privilege application role;
5. install backend and frontend;
6. run migrations;
7. create initial institution and first administrator through a one-time setup;
8. generate and retain installation ID;
9. activate license;
10. run smoke tests and create initial backup.

## 6. Backup and restore

Use scheduled logical backup plus retention policy and periodic restore tests. The backup service must require authorization and report success/failure in audit logs. Restore must stop writes, validate the backup, create a pre-restore snapshot, restore with a database maintenance script, run integrity checks, and restart services.

## 7. Updates

Updates require a confirmed backup and pre-update health check. Migrations run under a transaction where supported, and a failed migration prevents service start. Provide rollback instructions and tested migration/version compatibility.

## Phase 04 customer bundle

Build Angular with npm run build, then run .venv/bin/python scripts/package-customer.py customer.zip. This is a customer source and static-assets bundle. Prestage production wheels in an offline wheelhouse when deploying without registry access. Configure the vendor public-key JSON as a protected external file, apply Django migrations, seed roles, and serve the frontend and API on the same HTTPS origin. Back up PostgreSQL through the authorized server operator. Subscription state does not change the operator's database backup or restoration access.

## Academic records and backups

Apply the new migrations before serving Phase 05. Keep PostgreSQL and its backups access-restricted. Private normalized document bytes are in the database rather than a public media directory. Choose an HTTP request limit that accommodates up to six files under STUDENT_DOCUMENT_MAX_BYTES plus form overhead. Use disposable keys and an isolated database for workflow testing.

## Phase 07 fee management

See [Fee management](FEE_MANAGEMENT.md) for effective-dated structures, billing, PostgreSQL transactions, dynamic financial permissions, the signed fees entitlement and verification commands. Use UTF-8 PostgreSQL.

## Phase 08 examinations

See [Examination management](EXAMINATION_MANAGEMENT.md) for historic rosters, grading, marks verification, publication, corrections and the signed examinations entitlement.

## Phase 09 human resources and payroll

See [Human resources](HR_MANAGEMENT.md) for employment, staff attendance, compensation, protected payroll records and local deployment.

Before deploying Phase 10, record the pending migration plan and verify a
restorable encrypted PostgreSQL backup. Apply the additive migrations in the
normal migration workflow. If Phase 09 HR migrations 0012 and 0013 are pending,
include them in the reviewed plan. A signed `timetables` entitlement is
required to configure and publish schedules.

### Phase 10B backup and restore gate

Record a reviewed backup destination and recovery recipient in the institution's
secret management system. Restrict the destination and the PostgreSQL
authentication and GPG recovery material to the backup operator. Keep all of
them outside the source tree. Provision PostgreSQL authentication outside
the command line, such as a protected service definition and passfile.

Use a read-only dump of the reviewed operational database and stream it into
encryption. Use a separate fresh PostgreSQL cluster with a private socket for
restore verification. Before restoring, query `current_database()` and
`current_setting('data_directory')` on the destination and confirm they identify
the disposable cluster. Take note of the institution and critical record counts
at the snapshot. Compare the restored institution, counts and migration records,
and check that representative completed payroll and attendance records can be
read. Retain the encrypted backup and a checksum in the approved storage.

Example command pattern with operator-provisioned values:

```bash
set -o pipefail
umask 077
pg_dump --format=custom "service=$OPERATIONAL_READ_SERVICE" |
  gpg --batch --encrypt --recipient "$RECOVERY_RECIPIENT" --output "$ENCRYPTED_BACKUP"
gpg --batch --decrypt "$ENCRYPTED_BACKUP" |
  pg_restore --exit-on-error --no-owner --no-privileges --dbname="service=$DISPOSABLE_RESTORE_SERVICE"
```

Proceed with the reviewed migration plan only after the disposable restore
and readback succeed. The project migration script checks for missing
migration files and prints the plan before applying it.

### Phase 10C operator verification

Use `bash scripts/verify-encrypted-backup.sh --status` to check approved
configuration. Set `SMS_BACKUP_DIR`, `SMS_BACKUP_GNUPGHOME`,
`SMS_BACKUP_RECIPIENT` (the public fingerprint), `SMS_BACKUP_SOURCE_SERVICE`,
`SMS_BACKUP_EXPECTED_DB`, `SMS_BACKUP_EXPECTED_PORT`, and
`SMS_BACKUP_RETENTION_DAYS` through the local operator environment. Configure
the named PostgreSQL service and its credentials outside the repository.
Use a locally available private recovery key under an operator-owned
0700 keyring. The backup directory must also be operator-owned with mode 0700.

`--verify` creates a unique encrypted archive and tests recovery into a new
private Unix-socket PostgreSQL cluster. It compares representative table
counts and migration records and writes a checksum. The retention check
reports archives older than the configured window. Deletion is operator
controlled. The private restore destination is selected by the script.
Before an operational migration, also review restored institutional records
and the migration plan, then explicitly authorize deployment.

The Phase 10D read-only probe confirmed the configured operational identity
and eight pending migrations. Provision backup settings before attempting
operational restore verification and obtain separate authorization before
running the migration script.

### Phase 10E handoff

The read-only inventory confirmed the operational database identity and
eight pending migrations. Backup readiness remains blocked until the
operator provisions the settings above. Review the private destination,
recovery key and fingerprint, PostgreSQL service, expected source identity,
and retention policy before attempting an operational backup.

Once authorized backup configuration exists, run the status check, create
and verify the encrypted archive in the disposable restore environment,
validate restored schema and representative institutional records, and
review the operational migration plan. Obtain separate migration approval
before running the migration script. Afterward verify Django health and
readiness, migration consistency, timetable reads and representative
historical records. Preserve the verified archive and recovery instructions.
If recovery is needed, first test it in an isolated destination.

Phase 10F adds timetable migrations 0006 and 0007. The read-only inventory
found ten pending migrations. Complete the approved operational encrypted
backup and disposable restore procedure above before scheduling installation.
Applying migrations still requires separate operator authorization.
