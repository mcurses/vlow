#!/usr/bin/env bash
# Remove the vlow LaunchAgent. The .venv and project files are untouched.

set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/com.vlow.plist"

if launchctl print "gui/$UID/com.vlow" >/dev/null 2>&1; then
  launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
  echo "Unloaded com.vlow from launchd."
else
  echo "com.vlow was not loaded — nothing to unload."
fi

if [ -f "$PLIST" ]; then
  rm "$PLIST"
  echo "Removed $PLIST"
fi

echo "Done. Logs in ~/Library/Logs/vlow/ are kept; delete by hand if you want."
