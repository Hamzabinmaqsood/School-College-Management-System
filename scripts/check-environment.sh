#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

command -v python3 >/dev/null || { echo "Python 3 is missing"; exit 1; }
command -v psql >/dev/null || { echo "PostgreSQL CLI is missing"; exit 1; }
test -x .venv/bin/python || { echo "Run scripts/setup-dev.sh first"; exit 1; }
test -f backend/.env || { echo "backend/.env is missing"; exit 1; }
echo "Core environment files are present."
