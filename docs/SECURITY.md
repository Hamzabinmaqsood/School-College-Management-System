# Security Architecture

## 1. Authentication

Django's Argon2 password hashing is the preferred baseline. Enforce unique username/email where configured, account lockout/rate limiting, secure session or short-lived token storage, explicit logout, session rotation after login/password change, and MFA readiness.

Passwords are never logged or reversible. Default accounts are disabled or replaced during installation.

## 2. Authorization

Dynamic roles and permissions are stored in PostgreSQL. Authorization is based on permission codes plus institution and optional object scope. Both DRF permissions and domain services enforce backend checks; hiding navigation is not authorization.

## 3. Network

Bind PostgreSQL to loopback or the LAN interface only. Deny public exposure by firewall. Django should bind to a private LAN address or reverse proxy only. LAN TLS certificates and hostname configuration must be documented.

The frontend must not store secrets or signing private keys. Browser state is untrusted.

## 4. Input and output

- Django/DRF validation and ORM parameterization;
- strict file type, size, and storage restrictions;
- CSV formula-neutralization or safe export libraries;
- HTML sanitization for rich text;
- response content security policy and secure headers;
- no PII in URL parameters or logs.

## 5. Student data privacy

Collect only required fields, restrict PII permissions, mask identity/contact fields when appropriate, record PII access, define retention/deletion policies, and support lawful restricted deletion while preserving accounting and audit history.

## 6. Backups

Use PostgreSQL `pg_dump` or physical backup with encryption at rest. Backups include database configuration metadata and license state but never vendor private keys. Backup and restore requires elevated role and audit event.

## 7. Audit logs

Audit records are append-only at application level. Store actor, institution, action, object, timestamp, IP, request ID, and redacted structured changes. Database privileges prevent normal application users from deleting audit entries.

## 8. Dependency and update security

Pin production dependencies, scan updates, publish offline signed release metadata, verify package checksums, and maintain a tested upgrade/rollback procedure.

## 9. Known limitations

Offline signature enforcement can prevent accidental or ordinary use but cannot defeat a malicious administrator with full control of hardware, database, operating system, or application. Protect the server, limit administrator privileges, enable full-disk or database encryption when feasible, and maintain signed backups and audit logs.

## Phase 03 controls

Production uses Secure, HttpOnly, SameSite=Lax cookies. Configure HTTPS, allowed hosts, and a same-origin reverse proxy for LAN access. Permission checks enforce role activity, target authority, protected administrator roles, and final-administrator retention. Reset and deactivation revoke prior access. Logs record server-generated request IDs and safe change metadata. See AUTHENTICATION.md for configuration details.

## License trust separation

Only the vendor owns the Ed25519 private key. The customer verifier reads a preinstalled public manifest. License pages enforce session authentication, CSRF and RBAC. The packaging allowlist excludes vendor tooling, live environment files, development databases, and tests. It rejects recognized private-key material in selected content. Offline clock detection is best effort and the host operator remains a trust boundary.
