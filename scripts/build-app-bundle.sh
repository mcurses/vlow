#!/usr/bin/env bash
# Build a minimal vlow.app bundle so macOS shows "vlow" in Privacy &
# Security panels instead of the underlying "python3.12" binary.
#
# Output: $PROJECT_DIR/dist/vlow.app

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
APP="$PROJECT_DIR/dist/vlow.app"

if [ ! -x "$PYTHON" ]; then
  echo "Error: $PYTHON not found. Run 'uv sync' first." >&2
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

# CFBundleName drives the human-readable name in Privacy & Security.
# CFBundleIdentifier drives the TCC key; LSUIElement hides us from the Dock.
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>vlow</string>
    <key>CFBundleIdentifier</key>
    <string>com.vlow</string>
    <key>CFBundleName</key>
    <string>vlow</string>
    <key>CFBundleDisplayName</key>
    <string>vlow</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>vlow captures microphone audio for local transcription.</string>
</dict>
</plist>
EOF

cat > "$APP/Contents/PkgInfo" <<'EOF'
APPL????
EOF

# Launcher: bash → exec python -m vlow. The exec replaces bash with python
# in-place, but macOS still attributes the process to the parent bundle
# (com.vlow) for TCC purposes because the launch originated from inside
# the .app.
cat > "$APP/Contents/MacOS/vlow" <<EOF
#!/bin/bash
cd "$PROJECT_DIR"
exec "$PYTHON" -m vlow
EOF
chmod +x "$APP/Contents/MacOS/vlow"

# Touch the bundle so LaunchServices re-registers it.
touch "$APP"

echo "Built $APP"
echo "Bundle identifier: com.vlow"
