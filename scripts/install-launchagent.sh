#!/usr/bin/env bash
# Install a per-user LaunchAgent that keeps vlow running.
#
# Usage: scripts/install-launchagent.sh
#
# After install, vlow:
#   - starts at every login
#   - restarts automatically if it crashes
#   - logs to ~/Library/Logs/vlow/{vlow.log, vlow.err}
#
# The agent runs vlow via dist/vlow.app/Contents/MacOS/vlow so System
# Settings → Privacy & Security shows "vlow" (CFBundleName) instead of
# the raw "python3.12" binary.
#
# To stop the service:    launchctl bootout gui/$UID ~/Library/LaunchAgents/com.vlow.plist
# To start it again:      launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.vlow.plist
# To remove permanently:  scripts/uninstall-launchagent.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$PROJECT_DIR/dist/vlow.app"
APP_EXEC="$APP/Contents/MacOS/vlow"
PLIST="$HOME/Library/LaunchAgents/com.vlow.plist"
LOG_DIR="$HOME/Library/Logs/vlow"

# Build (or rebuild) the .app bundle so CFBundleName + paths are fresh.
"$PROJECT_DIR/scripts/build-app-bundle.sh"

if [ ! -x "$APP_EXEC" ]; then
  echo "Error: $APP_EXEC missing after build." >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vlow</string>

    <key>ProgramArguments</key>
    <array>
        <string>$APP_EXEC</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>Crashed</key>
        <true/>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/vlow.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/vlow.err</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "Wrote $PLIST"

# Replace any previous registration so config changes apply.
if launchctl print "gui/$UID/com.vlow" >/dev/null 2>&1; then
  launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
fi
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl enable "gui/$UID/com.vlow"
launchctl kickstart -k "gui/$UID/com.vlow"

echo "Loaded — vlow is now managed by launchd."
echo "Logs: $LOG_DIR"
echo "Tail with: tail -F $LOG_DIR/vlow.err"
