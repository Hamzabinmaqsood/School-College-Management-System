#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/dev-ports.sh"
check_dev_port Django "${DJANGO_PORT:-8000}" DJANGO_PORT
cd "$(dirname "$0")/.."
test -x .venv/bin/python || { echo "Run scripts/setup-dev.sh first" >&2; exit 1; }
test -f backend/.env || { echo "backend/.env is missing" >&2; exit 1; }
exec .venv/bin/python backend/manage.py runserver "127.0.0.1:${DJANGO_PORT:-8000}" "$@"
