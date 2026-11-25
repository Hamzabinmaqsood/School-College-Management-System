#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
demo_root="${XDG_DATA_HOME:-$HOME/.local/share}/school-management-demo-phase10g"
pgdata="$demo_root/postgres"
socket="$demo_root/socket"
port=55480
database=sms_phase10g_demo
role=sms_phase10g_demo_app
pg="$(pg_config --bindir)"
fixtures="$demo_root/fixtures.json"

umask 077
fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

[[ -x "$root/.venv/bin/python" && -f "$root/backend/.env" ]] ||
    fail "Expected the project virtualenv and backend/.env."
[[ ! -L "$demo_root" && ! -L "$pgdata" && ! -L "$socket" ]] ||
    fail "Refusing a symlinked demo database path."

mkdir -p "$demo_root" "$socket"
chmod 700 "$demo_root" "$socket"
if [[ -e "$pgdata" ]]; then
    [[ -f "$pgdata/PG_VERSION" ]] ||
        fail "The demo PostgreSQL path exists but is not an initialized cluster; inspect it first."
else
    mkdir -m 700 "$pgdata"
    "$pg/initdb" -D "$pgdata" -U postgres --auth-local=trust --auth-host=reject >/dev/null
fi

if ! "$pg/pg_ctl" -D "$pgdata" status >/dev/null 2>&1; then
    "$pg/pg_ctl" -D "$pgdata" -l "$demo_root/postgres.log" \
        -o "-c listen_addresses='' -k $socket -p $port" -w start >/dev/null
fi

identity=$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -h "$socket" -p "$port" \
    -U postgres -d postgres \
    -c "SELECT current_database() || '|' || current_setting('data_directory') || '|' || current_setting('listen_addresses') || '|' || (inet_server_addr() IS NULL)")
[[ "$identity" == "postgres|$pgdata||true" ]] ||
    fail "Refusing database provisioning: isolated cluster identity did not match."

"$pg/psql" -X -v ON_ERROR_STOP=1 -h "$socket" -p "$port" \
    -U postgres -d postgres <<SQL
SELECT 'CREATE ROLE $role LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$role');
\gexec
SELECT 'CREATE DATABASE $database OWNER $role'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$database');
\gexec
SQL

role_flags=$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -h "$socket" -p "$port" \
    -U postgres -d postgres \
    -c "SELECT rolsuper || '|' || rolcreatedb || '|' || rolcreaterole FROM pg_roles WHERE rolname = '$role'")
db_owner=$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -h "$socket" -p "$port" \
    -U postgres -d postgres \
    -c "SELECT datdba = (SELECT oid FROM pg_roles WHERE rolname = '$role') FROM pg_database WHERE datname = '$database'")
[[ "$role_flags" == "false|false|false" && "$db_owner" == "t" ]] ||
    fail "The demo database role or owner does not match the isolated configuration."

unset PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSERVICE PGSERVICEFILE
export DB_HOST="$socket" DB_PORT="$port" DB_NAME="$database" DB_USER="$role" DB_PASSWORD=""
export DB_CONN_MAX_AGE=0
export DJANGO_SETTINGS_MODULE=config.settings.development
export DJANGO_DEBUG=1 DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
export LICENSE_PUBLIC_KEYS_FILE="$demo_root/license-public-keys.json"

secret_file="$demo_root/django-secret"
if [[ ! -s "$secret_file" ]]; then
    "$root/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(64))' >"$secret_file"
    chmod 600 "$secret_file"
fi
export DJANGO_SECRET_KEY
DJANGO_SECRET_KEY="$(<"$secret_file")"

settings_check=$("$root/.venv/bin/python" "$root/backend/manage.py" shell -c \
    "from django.conf import settings; d=settings.DATABASES['default']; print('|'.join((d['HOST'], str(d['PORT']), d['NAME'], d['USER'])))" |
    tail -n 1)
[[ "$settings_check" == "$socket|$port|$database|$role" ]] ||
    fail "Django settings are not targeting the isolated demo database."

app_identity=$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -h "$socket" -p "$port" \
    -U "$role" -d "$database" \
    -c "SELECT current_database() || '|' || (inet_server_addr() IS NULL)")
[[ "$app_identity" == "$database|true" ]] ||
    fail "The demo application role did not connect through the private Unix socket."

cd "$root"
"$root/.venv/bin/python" backend/manage.py migrate --noinput

if [[ -e "$fixtures" ]]; then
    "$root/.venv/bin/python" -m json.tool "$fixtures" >/dev/null ||
        fail "Existing demo fixture file is invalid; inspect it before reseeding."
    printf 'Existing demo records preserved; migrations are current.\n'
else
    existing=$("$root/.venv/bin/python" backend/manage.py shell -c \
        "from apps.accounts.models import Institution; print(Institution.objects.exists())" |
        tail -n 1)
    [[ "$existing" == "False" ]] ||
        fail "Demo records exist without their fixture file; refusing to seed duplicates."
    SMS_PHASE10=1 SMS_PHASE10B=1 SMS_PHASE09_FIXTURES="$fixtures" \
        "$root/.venv/bin/python" backend/manage.py shell \
        < "$root/frontend/tests/browser/phase09/seed.py"
    chmod 600 "$fixtures" "$LICENSE_PUBLIC_KEYS_FILE"
fi

printf 'Demo database ready: %s\n' "$database"
printf 'Private PostgreSQL data: %s\n' "$pgdata"
printf 'Private Unix socket: %s (port %s; no TCP listener)\n' "$socket" "$port"
printf 'Synthetic admin credentials are in the mode-600 fixture file: %s\n' "$fixtures"
