#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/dev-ports.sh"
check_dev_port Angular "${ANGULAR_PORT:-4200}" ANGULAR_PORT
cd "$(dirname "$0")/../frontend"

supported_node() {
  command -v node >/dev/null && node -e '
    const [major, minor] = process.versions.node.split(".").map(Number);
    process.exit(process.platform === "linux" && major === 24 && minor >= 15 ? 0 : 1);
  '
}

if ! supported_node; then
  nvm_script="${NVM_DIR:-$HOME/.nvm}/nvm.sh"
  if [[ -s $nvm_script ]]; then
    set +u
    source "$nvm_script"
    nvm use --silent || true
    set -u
  fi
fi
if ! supported_node; then
  echo "Select Linux Node.js 24.15.0 or later in the 24.x series." >&2
  exit 1
fi
if [[ ! -f node_modules/@angular/cli/bin/ng.js ]]; then
  echo "Run npm ci inside frontend first." >&2
  exit 1
fi
exec node node_modules/@angular/cli/bin/ng.js serve --host localhost --port "${ANGULAR_PORT:-4200}" "$@"
