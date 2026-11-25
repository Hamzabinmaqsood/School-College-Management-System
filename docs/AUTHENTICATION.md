# Local authentication

Django authenticates usernames and passwords against the local PostgreSQL
installation. Server-side Django sessions work on a disconnected network and
allow logout and account changes to invalidate access without browser tokens.
Django validates passwords and stores their hashes. Angular holds current
identity and permission state in memory.

## Sessions and CSRF

The session and CSRF cookies use HttpOnly and SameSite=Lax. Production adds
Secure and requires HTTPS, including on a private LAN. Serve Angular and /api/
on the same origin. The development proxy preserves the browser host so Django
can validate Origin normally. When a reverse proxy terminates TLS, forward the
original Host and set DJANGO_TRUST_PROXY_HTTPS=True at the Django boundary.
Accept forwarded scheme headers only from a proxy that strips incoming copies.

GET /api/v1/auth/csrf/ sets the CSRF cookie and returns a masked token and
institution branding. Angular obtains the token before mutations and sends
X-CSRFToken. Django rotates the token at sign-in. The browser must hold the
cookie paired with the masked token. GET /auth/me/ verifies current identity and
grants. Protected APIs distinguish unauthenticated sessions from denied
permissions with HTTP 401 and 403 respectively.

Configure APP_SESSION_IDLE (1800 seconds by default) and APP_SESSION_MAX (43200)
in the server environment. User activity is recorded by authenticated API use.
Login throttles use PostgreSQL counters keyed by a server-side digest of
username and socket peer address. Defaults are 8 attempts per username and 60
per peer in 300 seconds. Configure APP_LOGIN_LIMIT, APP_LOGIN_IP_LIMIT, and
APP_LOGIN_WINDOW as needed. Incorrect, unknown, and disabled accounts receive
the same invalid-credentials response. Behind a reverse proxy the peer limit
applies to the proxy address. API access is revoked when a new password is set
or an account is deactivated. Reactivation requires a fresh session.

## First administrator and institution

    .venv/bin/python backend/manage.py migrate
    .venv/bin/python backend/manage.py seed_roles
    .venv/bin/python backend/manage.py setup_admin

The setup command requests a username and unechoed password in an interactive
terminal. It creates a non-superuser with the Institution Administrator role
when no active administrator exists. An existing active Django superuser can
sign in and configure the institution. Django Admin remains a local operator
interface for staff superusers. Existing sessions established before Phase 03
require a fresh sign-in.

At /login, sign in and complete /setup/institution when prompted. Settings
allows authorized users to update institution details. Images are checked and
re-encoded to a bounded PNG with metadata cleared. The public login surface
serves the branding fields and the canonical image. Contact details require
institution read access. Ur and RTL are supported as layout preferences. The
interface strings are currently in English.

## Manual acceptance checks

1. Start both servers and sign in to the application. Complete the institution
   form and check that its name and logo appear in the sidebar and sign-in page.
2. Create a custom role in Roles. Grant Dashboard View and a reserved module's
   View permission. Save and confirm the permission matrix changes.
3. Create a user in Users and assign the custom role and one other active role.
   Sign in as that user and change the temporary password when prompted.
4. Check that the assigned module is available, and open an unassigned route
   such as /users directly to verify denial. If you inspect the corresponding
   API request, an authenticated but unauthorized request returns HTTP 403.
5. Revoke a grant as an administrator, then check the user's navigation and
   access again. Review the events in Audit Logs and sign out.
