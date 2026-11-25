#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../.."
umask 077
sandbox="$(mktemp -d /tmp/sms-phase09.XXXXXX)"
pg="$(pg_config --bindir)"
api_pid=
ui_pid=
cleanup() {
    for pid in "$ui_pid" "$api_pid"; do
        if [[ -n $pid ]]; then kill "$pid" 2>/dev/null || true; fi
    done
    if [[ -f "$sandbox/django.log" ]]; then
        sed -nE 's/.*request method=([A-Z]+) path=([^ ]+) status=([0-9]+).*/\1 \2 \3/p'             "$sandbox/django.log" >"$SMS_PHASE09_EVIDENCE/http-statuses.log"
    fi
    "$pg/pg_ctl" -D "$sandbox/postgres" -m fast -w stop >/dev/null 2>&1 || true
    rm -rf -- "$sandbox"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

export DB_HOST="$sandbox" DB_PORT=55479 DB_USER="$USER" DB_NAME=sms_phase09_browser
export DB_CONN_MAX_AGE=0
export DJANGO_PORT="${SMS_PHASE09_DJANGO_PORT:-8039}"
export ANGULAR_PORT="${SMS_PHASE09_ANGULAR_PORT:-4239}"
source scripts/dev-ports.sh
if [[ $DJANGO_PORT == "$ANGULAR_PORT" ]]; then
    printf 'The browser suite requires distinct Django and Angular ports.\n' >&2
    exit 1
fi
check_dev_port Django "$DJANGO_PORT" SMS_PHASE09_DJANGO_PORT
check_dev_port Angular "$ANGULAR_PORT" SMS_PHASE09_ANGULAR_PORT
export LICENSE_PUBLIC_KEYS_FILE="$sandbox/keys.json"
export SMS_PHASE09_FIXTURES="$sandbox/fixtures.json"
export SMS_PHASE09_BASE_URL="http://127.0.0.1:$ANGULAR_PORT"
export SMS_PHASE09_EVIDENCE="${SMS_PHASE09_EVIDENCE:-$(mktemp -d /tmp/sms-phase09-evidence.XXXXXX)}"
mkdir -p "$SMS_PHASE09_EVIDENCE"

"$pg/initdb" -D "$sandbox/postgres" -A trust -U "$DB_USER" >/dev/null
"$pg/pg_ctl" -D "$sandbox/postgres" -l "$sandbox/postgres.log" \
    -o "-c listen_addresses='' -k $sandbox -p $DB_PORT" -w start >/dev/null
"$pg/createdb" -h "$DB_HOST" -p "$DB_PORT" "$DB_NAME"
identity=$("$pg/psql" -XAt -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" \
    -c "SELECT current_database() || '|' || current_setting('data_directory') || '|' || (inet_server_addr() IS NULL)")
if [[ $identity != "$DB_NAME|$sandbox/postgres|true" ]]; then
    printf 'Could not verify the isolated PostgreSQL cluster.\n' >&2
    exit 1
fi
if [[ ${SMS_PHASE09_PG_REGRESSION:-0} == 1 ]]; then
    .venv/bin/python -m pytest --ds=config.settings.development -q
fi
.venv/bin/python backend/manage.py migrate --noinput >"$sandbox/migrate.log"
.venv/bin/python backend/manage.py shell < frontend/tests/browser/phase09/seed.py >"$sandbox/seed.log" 2>&1 || {
    cat "$sandbox/seed.log"
    exit 1
}
if [[ -n ${SMS_PHASE09_LEAVE:-} ]]; then
    export SMS_PHASE09_LEAVE_CLOCK="$sandbox/leave-date"
    printf '%s\n' '2025-06-30' >"$SMS_PHASE09_LEAVE_CLOCK"
    DJANGO_SETTINGS_MODULE=leave_clock PYTHONPATH="$PWD/frontend/tests/browser/phase09:${PYTHONPATH:-}" \
        bash scripts/start-backend.sh --noreload >"$sandbox/django.log" 2>&1 &
else
    bash scripts/start-backend.sh --noreload >"$sandbox/django.log" 2>&1 &
fi
api_pid=$!
(cd frontend && npm run build) >"$sandbox/build.log" 2>&1 || { cat "$sandbox/build.log"; exit 1; }
node frontend/tests/browser/phase09/serve.mjs >"$sandbox/angular.log" 2>&1 &
ui_pid=$!
for attempt in {1..80}; do
    if curl -fsS "$SMS_PHASE09_BASE_URL/api/v1/ready/" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$api_pid" "$ui_pid" 2>/dev/null || [[ $attempt == 80 ]]; then
        tail -30 "$sandbox/django.log" "$sandbox/angular.log"
        exit 1
    fi
    sleep 1
done
# The seeded institution UUID is unique to this run. Verify the proxy actually
# reaches it before giving the browser fixture credentials.
curl -fsS "$SMS_PHASE09_BASE_URL/api/v1/auth/csrf/" | python3 -c '
import json, os, sys
with open(os.environ["SMS_PHASE09_FIXTURES"]) as source:
    expected = json.load(source)["institution"]
actual = (json.load(sys.stdin).get("institution") or {}).get("id")
if actual != expected:
    sys.exit("Acceptance proxy did not reach the isolated fixture institution.")
'
printf 'Browser evidence: %s\n' "$SMS_PHASE09_EVIDENCE"
(cd frontend && node_modules/.bin/playwright test --config tests/browser/phase09/playwright.config.mjs "$@")
