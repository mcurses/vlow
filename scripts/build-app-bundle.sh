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

# Homebrew's binaries load libpython through the *versioned* Cellar directory
# (.../Cellar/python@3.12/3.12.14/Frameworks/...), and Homebrew deletes that
# directory on the next patch bump. A bundle built today stops launching the
# moment `brew upgrade` moves 3.12.14 to 3.12.15, leaving only a dyld "Library
# not loaded" in the LaunchAgent log. Rewrite those references onto opt/, the
# symlink Homebrew keeps pointing at the current patch release. Non-Homebrew
# interpreters (uv's python-build-standalone) load libpython through
# @executable_path and pass through untouched.
stable_python_path() {
  printf '%s\n' "$1" | sed -E 's#^(/[^ ]*)/Cellar/(python@[0-9.]+)/[^/]+/#\1/opt/\2/#'
}

# Relink and re-sign in a staging dir, then move the finished binary in.
# codesign reads a path inside an .app as "seal the whole bundle", and sealing
# cannot work here: Contents/lib deliberately points at the checkout's .venv,
# outside the bundle. Signing the bare Mach-O gives us the same shape of
# signature the copied Homebrew binary already carried.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PYTHON_REAL="$(readlink -f "$PYTHON")"
PYTHON_INNER="$(dirname "$PYTHON_REAL")/../Resources/Python.app/Contents/MacOS/Python"
if [ -x "$PYTHON_INNER" ]; then
  cp "$PYTHON_INNER" "$STAGE/vlow"
else
  cp "$PYTHON_REAL" "$STAGE/vlow"
fi
chmod +x "$STAGE/vlow"

relinked=0
while read -r dep; do
  stable="$(stable_python_path "$dep")"
  [ "$stable" = "$dep" ] && continue
  install_name_tool -change "$dep" "$stable" "$STAGE/vlow"
  relinked=1
done < <(otool -L "$STAGE/vlow" | sed -n 's/^\t\([^ ]*\).*/\1/p')

# install_name_tool invalidates the signature the binary inherited from
# Homebrew, and macOS will not launch an arm64 binary whose signature does not
# match its bytes.
if [ "$relinked" -eq 1 ]; then
  codesign --force --sign - --identifier com.vlow "$STAGE/vlow"
fi

mv "$STAGE/vlow" "$APP/Contents/MacOS/vlow"
cp "$PROJECT_DIR/.venv/pyvenv.cfg" "$APP/Contents/pyvenv.cfg"

# Contents/lib has to serve two masters: it points site-packages at the
# real .venv, and for non-framework interpreters (uv's
# python-build-standalone builds) it also has to hold libpython, which
# the copied binary loads via @executable_path/../lib. So build it as a
# real directory of symlinks rather than one symlink to .venv/lib.
mkdir -p "$APP/Contents/lib"
for entry in "$PROJECT_DIR/.venv/lib/"*; do
  [ -e "$entry" ] || continue
  ln -sfn "$entry" "$APP/Contents/lib/$(basename "$entry")"
done
for dylib in "$(dirname "$PYTHON_REAL")/../lib/"libpython*.dylib; do
  [ -e "$dylib" ] || continue
  ln -sfn "$(stable_python_path "$(readlink -f "$dylib")")" "$APP/Contents/lib/$(basename "$dylib")"
done

# Touch the bundle so LaunchServices re-registers it.
touch "$APP"

echo "Built $APP"
echo "Bundle identifier: com.vlow"
