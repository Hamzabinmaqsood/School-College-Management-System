#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest
cd frontend
test -d node_modules && npm test -- --watch=false || true
