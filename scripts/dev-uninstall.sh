#!/usr/bin/env bash
# Undo scripts/dev-install.sh: stop the agent, forget it at login, remove the
# CLI symlink. Logs in ~/Library/Logs/vlow are kept.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"

launchctl bootout "gui/$(id -u)/com.vlow" 2>/dev/null || true
"$PYTHON" -c 'from vlow import cli_link, login_item; login_item.set_enabled(False); cli_link.uninstall()'

echo "vlow no longer starts at login. Logs in ~/Library/Logs/vlow are kept."
