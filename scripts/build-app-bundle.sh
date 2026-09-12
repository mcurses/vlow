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

# Same version string as the release DMG, so the updater can compare.
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$PROJECT_DIR/pyproject.toml")"

# The SwiftUI overlay module lives alongside the bundle in dist/.
"$PROJECT_DIR/scripts/build-glass.sh"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$PROJECT_DIR/assets/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"

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
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleDisplayName</key>
    <string>vlow</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
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

# The bundle executable must be the real interpreter binary, not a shell
# script that exec's it: TCC attributes permissions to the running
# process's executable path, so a launcher shows up as "python3.12" in
# Privacy & Security while a python binary living inside the bundle shows
# up as "vlow". Framework builds add a twist: bin/python3.12 is a stub
# that re-execs Resources/Python.app/Contents/MacOS/Python (so GUI code
# gets a bundle) — copy that inner binary, which doesn't re-exec and is
# happy inside vlow.app. The copy is turned into a venv-equivalent
# interpreter by the pyvenv.cfg next to it (marks Contents/ as the venv
# prefix) and the lib symlink (points site-packages at the real .venv).
PYTHON_REAL="$(readlink -f "$PYTHON")"
PYTHON_INNER="$(dirname "$PYTHON_REAL")/../Resources/Python.app/Contents/MacOS/Python"
if [ -x "$PYTHON_INNER" ]; then
  cp "$PYTHON_INNER" "$APP/Contents/MacOS/vlow"
else
  cp "$PYTHON_REAL" "$APP/Contents/MacOS/vlow"
fi
chmod +x "$APP/Contents/MacOS/vlow"
cp "$PROJECT_DIR/.venv/pyvenv.cfg" "$APP/Contents/pyvenv.cfg"
ln -sfn "$PROJECT_DIR/.venv/lib" "$APP/Contents/lib"

# Touch the bundle so LaunchServices re-registers it.
touch "$APP"

echo "Built $APP"
echo "Bundle identifier: com.vlow"
