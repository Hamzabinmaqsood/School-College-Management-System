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

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

[[ -f "$pgdata/PG_VERSION" ]] ||
    fail "Run bash scripts/setup-demo-db.sh before starting the demo."
[[ -s "$demo_root/django-secret" && -s "$demo_root/license-public-keys.json" &&
   -s "$demo_root/fixtures.json" ]] ||
    fail "Demo credentials or fixtures are missing; inspect the demo data directory."
[[ ! -L "$demo_root" && ! -L "$pgdata" && ! -L "$socket" ]] ||
    fail "Refusing a symlinked demo database path."

if ! "$pg/pg_ctl" -D "$pgdata" status >/dev/null 2>&1; then
    "$pg/pg_ctl" -D "$pgdata" -l "$demo_root/postgres.log" \
        -o "-c listen_addresses='' -k $socket -p $port" -w start >/dev/null
fi

identity=$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -h "$socket" -p "$port" \
    -U postgres -d postgres \
    -c "SELECT current_database() || '|' || current_setting('data_directory') || '|' || current_setting('listen_addresses') || '|' || (inet_server_addr() IS NULL)")
[[ "$identity" == "postgres|$pgdata||true" ]] ||
    fail "Refusing startup: PostgreSQL is not the isolated demo cluster."

unset PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSERVICE PGSERVICEFILE
export DB_HOST="$socket" DB_PORT="$port" DB_NAME="$database" DB_USER="$role" DB_PASSWORD=""
export DB_CONN_MAX_AGE=0
export DJANGO_SETTINGS_MODULE=config.settings.development
export DJANGO_DEBUG=1 DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
export LICENSE_PUBLIC_KEYS_FILE="$demo_root/license-public-keys.json"
export DJANGO_SECRET_KEY
DJANGO_SECRET_KEY="$(<"$demo_root/django-secret")"
export DJANGO_PORT="${SMS_DEMO_DJANGO_PORT:-8040}"
export ANGULAR_PORT="${SMS_DEMO_ANGULAR_PORT:-4240}"

settings_check=$("$root/.venv/bin/python" "$root/backend/manage.py" shell -c \
    "from django.conf import settings; d=settings.DATABASES['default']; print('|'.join((d['HOST'], str(d['PORT']), d['NAME'], d['USER'])))" |
    tail -n 1)
[[ "$settings_check" == "$socket|$port|$database|$role" ]] ||
    fail "Django settings are not targeting the isolated demo database."

connection_check=$("$root/.venv/bin/python" "$root/backend/manage.py" shell -c \
    "from django.db import connection; c=connection.cursor(); c.execute('SELECT current_database(), inet_server_addr() IS NULL'); print('|'.join(map(str, c.fetchone())))" |
    tail -n 1)
[[ "$connection_check" == "$database|True" ]] ||
    fail "Django did not connect to the isolated demo database over its private socket."

if [[ "${1:-}" == "--check" ]]; then
    [[ $# == 1 ]] || fail "Usage: scripts/start-demo.sh [--check]"
    printf 'Demo backend is ready for %s on its private socket.\n' "$database"
    exit 0
fi
[[ $# == 0 ]] || fail "Usage: scripts/start-demo.sh [--check]"

exec bash "$root/scripts/start-dev.sh"
