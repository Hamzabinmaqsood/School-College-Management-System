#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cd backend
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py migrate --plan
../.venv/bin/python manage.py migrate
