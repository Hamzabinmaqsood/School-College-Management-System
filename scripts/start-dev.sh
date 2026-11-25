#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/dev-ports.sh
export DJANGO_PORT="${DJANGO_PORT:-8000}" ANGULAR_PORT="${ANGULAR_PORT:-4200}"
if [[ $DJANGO_PORT == "$ANGULAR_PORT" ]]; then
    printf 'Django and Angular need distinct ports. Choose separate DJANGO_PORT and ANGULAR_PORT values.\n' >&2
    exit 1
fi
conflict=0
check_dev_port Django "$DJANGO_PORT" DJANGO_PORT || conflict=1
check_dev_port Angular "$ANGULAR_PORT" ANGULAR_PORT || conflict=1
if (( conflict )); then
    printf 'For example, DJANGO_PORT=8001 ANGULAR_PORT=4201 bash scripts/start-dev.sh\n' >&2
    exit 1
fi

backend_pid=
frontend_pid=
cleanup() {
  trap - EXIT
  for pid in "$backend_pid" "$frontend_pid"; do
    if [[ -n $pid ]]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

bash scripts/start-backend.sh --noreload &
backend_pid=$!
bash scripts/start-frontend.sh &
frontend_pid=$!
wait -n "$backend_pid" "$frontend_pid"
