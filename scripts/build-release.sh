#!/usr/bin/env bash
# Build a self-contained, redistributable vlow.app and wrap it in a DMG.
#
#   dist/release/vlow.app          the bundle
#   dist/vlow-<version>-arm64.dmg  what people download
#
# Unlike scripts/build-app-bundle.sh (a thin wrapper around the local .venv
# for launchd), this bundle carries its own CPython (python-build-standalone
# via uv), all dependencies, the glass dylib and the icons, so it runs on any
# Apple Silicon Mac with macOS 14+ (the glass overlay needs macOS 26).
#
# Environment:
#   VLOW_VERSION          version string for Info.plist / DMG name
#                         (default: version from pyproject.toml)
#   VLOW_SIGN_IDENTITY    codesign identity; default "-" = ad-hoc.
#                         Set to "Developer ID Application: …" for a real
#                         signature (enables hardened runtime + timestamp).
#   VLOW_NOTARIZE=1       after signing, notarize + staple the DMG. Needs
#                         APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD.
#   VLOW_SKIP_DMG=1       stop after the .app (faster local iteration)
#
# Requirements: uv, Xcode Command Line Tools (clang, swiftc w/ macOS 26 SDK).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$PROJECT_DIR/dist/release"
APP="$OUT_DIR/vlow.app"
CONTENTS="$APP/Contents"
PY_DST="$CONTENTS/Resources/python"
PY_MINOR="3.12"
MIN_MACOS="14.0"
ARCH="arm64"

VERSION="${VLOW_VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' "$PROJECT_DIR/pyproject.toml")}"
VERSION="${VERSION#v}"
SIGN_IDENTITY="${VLOW_SIGN_IDENTITY:--}"
DMG="$PROJECT_DIR/dist/vlow-$VERSION-$ARCH.dmg"

log() { printf '\n==> %s\n' "$*"; }

command -v uv >/dev/null || { echo "Error: uv not found" >&2; exit 1; }
command -v clang >/dev/null || { echo "Error: clang not found — install Xcode CLT" >&2; exit 1; }

# --- 1. Native pieces -------------------------------------------------------
log "Building glass overlay dylib"
"$PROJECT_DIR/scripts/build-glass.sh"

# --- 2. Relocatable CPython --------------------------------------------------
log "Fetching python-build-standalone $PY_MINOR via uv"
uv python install "$PY_MINOR"
# cd away from the repo so uv doesn't hand us the project .venv.
PY_SRC="$(cd / && { uv python find --managed-python "$PY_MINOR" 2>/dev/null \
      || uv python find --python-preference only-managed "$PY_MINOR"; })"
# Physical path: on CI the install dir is reached through a symlink, and
# `cp -R` of a symlinked directory copies the *link*, leaving the bundle
# pointing outside itself (codesign: "invalid destination for symbolic link").
PY_ROOT="$(cd "$(dirname "$PY_SRC")/.." && pwd -P)"
echo "    using $PY_ROOT"

rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources" "$CONTENTS/Frameworks"
cp -R "$PY_ROOT/" "$PY_DST"
[ -d "$PY_DST" ] && [ ! -L "$PY_DST" ] || { echo "Error: $PY_DST is not a real directory" >&2; exit 1; }
# Our copy is not uv-managed anymore; let `uv pip` install into it.
rm -f "$PY_DST/lib/python$PY_MINOR/EXTERNALLY-MANAGED"
PY="$PY_DST/bin/python$PY_MINOR"
PY_PREFIX="$("$PY" -c 'import sys; print(sys.prefix)')"
case "$PY_PREFIX" in
  "$PY_DST"*) ;;
  *) echo "Error: bundled python resolves to $PY_PREFIX, not inside the bundle" >&2; exit 1 ;;
esac

# --- 3. Launcher -------------------------------------------------------------
# Must be compiled while include/ still exists (it is trimmed below).
log "Compiling launcher"
clang -O2 -mmacosx-version-min="$MIN_MACOS" -arch "$ARCH" \
  -I"$PY_DST/include/python$PY_MINOR" -L"$PY_DST/lib" -lpython"$PY_MINOR" \
  -o "$CONTENTS/MacOS/vlow" "$PROJECT_DIR/native/launcher.c"
# libpython's install name is a build-machine path; point the launcher at the
# copy inside the bundle instead.
OLD_LIBPY="$(otool -L "$CONTENTS/MacOS/vlow" | awk '/libpython/{print $1}')"
install_name_tool -change "$OLD_LIBPY" \
  "@executable_path/../Resources/python/lib/libpython$PY_MINOR.dylib" \
  "$CONTENTS/MacOS/vlow"

# --- 4. Dependencies (from uv.lock) ------------------------------------------
log "Installing locked dependencies into the bundle"
REQ="$(mktemp -t vlow-req).txt"
(cd "$PROJECT_DIR" && uv export --frozen --no-dev --no-emit-project --no-hashes -o "$REQ" >/dev/null)
uv pip install --python "$PY" --compile-bytecode -r "$REQ"
# --no-cache: uv keys source-tree builds on pyproject.toml, not on the
# sources, so a cached wheel would silently ship stale code.
uv pip install --python "$PY" --compile-bytecode --no-deps --no-cache "$PROJECT_DIR"
rm -f "$REQ"

# torch is a declared mlx-whisper dependency but only imported by its
# PyTorch → MLX weight-conversion module, which vlow never touches. ~400 MB.
log "Removing torch (unused at runtime)"
uv pip uninstall --python "$PY" torch sympy mpmath networkx

# --- 5. Trim + precompile ------------------------------------------------------
log "Trimming the Python tree"
"$PY" -m compileall -q -j0 "$PY_DST/lib/python$PY_MINOR" >/dev/null || true
(
  cd "$PY_DST"
  rm -rf bin include share lib/pkgconfig lib/tcl8 lib/tcl8.6 lib/tk8.6 lib/itcl* lib/thread* lib/libtcl* lib/libtk*
  cd "lib/python$PY_MINOR"
  rm -rf test idlelib tkinter turtledemo ensurepip lib-dynload/_tkinter* config-*
)

# --- 6. Resources + Info.plist ------------------------------------------------
log "Copying resources"
cp "$PROJECT_DIR/assets/AppIcon.icns" "$CONTENTS/Resources/AppIcon.icns"
cp -R "$PROJECT_DIR/assets/menubar" "$CONTENTS/Resources/menubar"
cp "$PROJECT_DIR/dist/libVlowGlass.dylib" "$CONTENTS/Frameworks/libVlowGlass.dylib"

cat > "$CONTENTS/Info.plist" <<PLIST
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
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>LSMinimumSystemVersion</key>
    <string>$MIN_MACOS</string>
    <key>LSArchitecturePriority</key>
    <array><string>$ARCH</string></array>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>vlow captures microphone audio for transcription.</string>
    <key>NSHumanReadableCopyright</key>
    <string>vlow — local voice dictation</string>
</dict>
</plist>
PLIST
printf 'APPL????' > "$CONTENTS/PkgInfo"

# --- 7. Sign -----------------------------------------------------------------
log "Signing (identity: $SIGN_IDENTITY)"
SIGN_ARGS=(--force --sign "$SIGN_IDENTITY")
if [ "$SIGN_IDENTITY" != "-" ]; then
  SIGN_ARGS+=(--timestamp --options runtime)
fi
# Every Mach-O inside must carry a signature before the outer bundle is sealed
# (notarization rejects unsigned nested code; ad-hoc keeps Gatekeeper's
# "damaged app" check quiet).
find "$CONTENTS/Resources/python" -type f \( -name '*.so' -o -name '*.dylib' \) -print0 \
  | xargs -0 codesign "${SIGN_ARGS[@]}"
codesign "${SIGN_ARGS[@]}" "$CONTENTS/Frameworks/libVlowGlass.dylib"
codesign "${SIGN_ARGS[@]}" --entitlements "$PROJECT_DIR/scripts/entitlements.plist" "$APP"
codesign --verify --deep --strict --verbose=1 "$APP"

# --- 8. Smoke test -------------------------------------------------------------
log "Smoke test: importing the app stack from inside the bundle"
"$CONTENTS/MacOS/vlow" -c "
import sys
import vlow.app, vlow.overlay, vlow.settings_window, vlow.updater, vlow.whisper_model, vlow.transcribe_mlx, vlow.stream_aai
import mlx.core, mlx_whisper, sounddevice, rumps, numba
from vlow import resources
assert resources.bundle_contents() is not None, sys.executable
assert resources.glass_dylib().exists(), resources.glass_dylib()
assert resources.menubar_icon_dir().joinpath('mic.png').exists()
print('   python', sys.version.split()[0], '| mlx', mlx.core.__version__, '| ok')
"
echo "Built $APP ($(du -sh "$APP" | cut -f1))"

[ "${VLOW_SKIP_DMG:-}" = "1" ] && exit 0

# --- 9. DMG --------------------------------------------------------------------
log "Creating DMG"
STAGING="$(mktemp -d -t vlow-dmg)"
cp -R "$APP" "$STAGING/vlow.app"
ln -s /Applications "$STAGING/Applications"
rm -f "$DMG"
# hdiutil occasionally fails with "Resource busy" on CI runners; retry.
for attempt in 1 2 3; do
  if hdiutil create -volname "vlow $VERSION" -srcfolder "$STAGING" -ov -format UDZO \
       -imagekey zlib-level=9 "$DMG" >/dev/null; then break; fi
  [ "$attempt" = 3 ] && { echo "hdiutil create failed" >&2; exit 1; }
  sleep 5
done
rm -rf "$STAGING"
if [ "$SIGN_IDENTITY" != "-" ]; then
  codesign --force --sign "$SIGN_IDENTITY" --timestamp "$DMG"
fi

if [ "${VLOW_NOTARIZE:-}" = "1" ]; then
  log "Notarizing"
  : "${APPLE_ID:?}" "${APPLE_TEAM_ID:?}" "${APPLE_APP_PASSWORD:?}"
  xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" --wait
  xcrun stapler staple "$DMG"
fi

echo "Built $DMG ($(du -sh "$DMG" | cut -f1))"
