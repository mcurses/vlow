#!/usr/bin/env bash
# Run this checkout the way an installed vlow runs: as a LaunchAgent, from an
# .app bundle (so Privacy & Security says "vlow", not "python3.12"), with the
# `vlow` CLI on your PATH.
#
# This is a development task, not a vlow feature — everything vlow itself can
# do is a subcommand of `vlow` (start, stop, restart, status, logs). Ordinary
# users get all of this from the DMG plus the Settings toggle.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Error: $PYTHON not found. Run 'uv sync' first." >&2
  exit 1
fi

"$PROJECT_DIR/scripts/build-app-bundle.sh"

# login_item is the one module that writes the plist; dev-uninstall.sh and the
# Settings toggle go through the same call.
"$PYTHON" -c 'from vlow import cli_link, login_item; login_item.set_enabled(True); cli_link.ensure()'

launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.vlow.plist" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.vlow.plist"
launchctl kickstart -k "gui/$(id -u)/com.vlow"

echo
echo "vlow is running and will start at login."
"$PYTHON" -m vlow status
