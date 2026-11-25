# Environment Setup

Open the repository from Ubuntu so VS Code runs extensions and terminals in WSL.

    cd ~/school-management-system
    code .

Check for **WSL: Ubuntu** in the VS Code status bar. In the integrated terminal,
run the following to verify that it reports Ubuntu. Use that Bash terminal for
development commands.

    printf '%s\n' "$WSL_DISTRO_NAME"

## Verified toolchain

- Python 3.14.4, Django 5.2.19, Django REST Framework 3.18.3, and psycopg 3.3.9
- PostgreSQL 18.6 on 127.0.0.1:5433
- Linux Node.js 24.22.3 LTS, npm 11.19.1, and nvm 0.40.3
- Angular, CLI, Material, and CDK 22.3.0, TypeScript 6.0.3, ESLint 10.15.0, and Vitest 4.1.12

The PostgreSQL application role and database in this workspace are provisioned.
The migration history includes AuditEvent migration 0002 and has no outstanding
model changes.

## PostgreSQL

Keep the generated values in backend/.env. For a fresh instance that needs local provisioning, run:

    bash scripts/setup-database.sh

The script requests sudo in the Ubuntu terminal. It checks for the dedicated
role and database before creating either, verifies application authentication
and schema privileges, and keeps the password out of arguments and output.

## Isolated persistent demo database

For manual acceptance testing, use the separate demo cluster instead of the
application database above. It is created under
`~/.local/share/school-management-demo-phase10g`, listens only on its private
Unix socket, and uses database `sms_phase10g_demo` on socket port 55480. The
setup command applies project migrations and seeds disposable Browser Academy
records. It creates a new Django secret and a test-only signing key; it does
not read or use production signing keys or modify `backend/.env`.

Run once in Ubuntu WSL:

    cd ~/school-management-system
    source "$HOME/.nvm/nvm.sh"
    nvm use
    bash scripts/setup-demo-db.sh
    bash scripts/start-demo.sh --check

Start the application against that database. The default ports are 8040
(backend) and 4240 (frontend). They are occupied on this WSL host by an
existing service, so use these verified alternate ports without stopping or
reusing that service:

    source "$HOME/.nvm/nvm.sh"
    nvm use
    SMS_DEMO_DJANGO_PORT=8041 SMS_DEMO_ANGULAR_PORT=4241 bash scripts/start-demo.sh

Open http://127.0.0.1:4241/login. Sign in as `fixture-admin`; its randomly
generated password is in `accounts.admin.password` in
`~/.local/share/school-management-demo-phase10g/fixtures.json`. The fixture
file is mode 600. Open it locally to retrieve the password; do not put it in a
shell command, chat, screenshot, or application log. The demo license is
synthetic and signed by a test-only key. Use the Browser Academy records for
manual acceptance and keep all changes in this disposable database.

Stop the application with Ctrl+C. To stop PostgreSQL while preserving demo
data:

    "$(pg_config --bindir)/pg_ctl" -D "$HOME/.local/share/school-management-demo-phase10g/postgres" -m fast -w stop

`start-demo.sh` pins Django's database settings to this database and refuses
startup unless the PostgreSQL data directory, private socket, non-TCP listener,
database and role match the expected demo identity. Do not use
`scripts/setup-database.sh` for demo work; it provisions the separate
school-management application database on port 5433.

## Node and Angular

Use the Node version in the repository's .nvmrc. The current installation was
verified against the official Node.js SHA-256 checksum. If setting up a new
WSL environment and direct Linux downloads time out, use the procedure below.

Download the official Linux x64 archive and its checksums from Windows
PowerShell.

    $base = 'https://nodejs.org/dist/v24.22.3'
    curl.exe -fL --connect-timeout 10 --max-time 600 --retry 1 "$base/node-v24.22.3-linux-x64.tar.xz" -o "$env:USERPROFILE/Downloads/node-v24.22.3-linux-x64.tar.xz"
    curl.exe -fL --connect-timeout 10 --max-time 60 "$base/SHASUMS256.txt" -o "$env:USERPROFILE/Downloads/SHASUMS256.txt"

Then verify and install it in Ubuntu. The installation below uses nvm's version
directory so the same runtime is available in future Ubuntu terminals.

    (
      set -euo pipefail
      cd /mnt/c/Users/Malik/Downloads
      archive=node-v24.22.3-linux-x64.tar.xz
      awk -v archive="$archive" '$2 == archive' SHASUMS256.txt | sha256sum -c -
      node_root="$HOME/.nvm/versions/node/v24.22.3"
      mkdir -p "$HOME/.nvm/versions/node"
      mkdir "$node_root"
      tar -xJf "$archive" --strip-components=1 -C "$node_root"
    )
    source "$HOME/.nvm/nvm.sh"
    nvm use 24.22.3
    node --version
    npm --version
    which node npm

## Development startup

    cd ~/school-management-system
    source "$HOME/.nvm/nvm.sh"
    nvm use
    (cd frontend && npm ci)
    bash scripts/start-dev.sh

Open http://localhost:4200. Django serves http://127.0.0.1:8000, and the Angular
development proxy forwards relative /api requests there. To override ports, set
DJANGO_PORT and ANGULAR_PORT when running start-dev.sh. If Django is already
running, use bash scripts/start-frontend.sh on its own and set DJANGO_PORT to
the port Django is using.

## Verification

    .venv/bin/python backend/manage.py check
    .venv/bin/python backend/manage.py migrate --check
    .venv/bin/python backend/manage.py makemigrations --check --dry-run
    .venv/bin/python -m pytest
    .venv/bin/python -m pytest --ds=config.settings.development backend/tests/test_postgresql_integration.py
    .venv/bin/ruff check backend
    (cd frontend && npm run typecheck && npm run lint && npm test && npm run build)

Phase 02C verification passed on 19 November 2026. The Django suite passed five
tests with the two PostgreSQL-only tests skipped under SQLite. Both read-only
PostgreSQL checks passed when run against development settings. Django checks,
migration consistency, Ruff, clean npm lockfile installation, TypeScript, ESLint,
four frontend tests, and the Angular production build passed. Chrome verified
desktop and mobile rendering, live status, navigation, the chart filter, and
theme switching. The alternate-port startup test verified the API proxy and
shutdown of both servers.

## Offline deployment

Build with npm run build in frontend and serve frontend/dist/school/browser.
Configure the local web server to forward /api/ to Django on the same origin and
to serve index.html for Angular routes. Use separate Django production settings.
The frontend bundles its icons, font, scripts, and styles. The installation and
build require packages in the npm cache or access to a registry. Serving the
built application and its local API does not require internet access.

## Phase 03 setup and checks

Install Python requirements, migrate, run seed_roles, and run setup_admin as shown in README.md. Start both servers with bash scripts/start-dev.sh and open http://localhost:4200/login. Pillow 13.0.0 validates institution logos. Unit checks use .venv/bin/python -m pytest, .venv/bin/ruff check backend, and npm run typecheck, npm run lint, npm test, npm run build in frontend/. For PostgreSQL, run pytest --ds=config.settings.development against an isolated cluster via DB_HOST, DB_PORT, DB_NAME, and DB_USER. Apply migrations to the isolated database before running the live read-only checks.

### Phase 03 verification

On 21 November 2026, the SQLite suite passed 12 tests and skipped the two
PostgreSQL-only checks. All 14 backend tests passed against an isolated
PostgreSQL cluster. Angular passed 10 tests, TypeScript, ESLint, and the
production build. Chrome verified the administrator and restricted-user
workflows using isolated PostgreSQL records. The development proxy accepted
same-origin CSRF and rejected a mutation with the token omitted.
