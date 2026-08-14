#!/usr/bin/env bash
# Compile the SwiftUI glass overlay module to dist/libVlowGlass.dylib.
# Requires the Xcode (or CLT) Swift toolchain with the macOS 26 SDK.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$PROJECT_DIR/dist/libVlowGlass.dylib"

if ! command -v swiftc >/dev/null; then
  echo "Error: swiftc not found — install Xcode Command Line Tools." >&2
  exit 1
fi

mkdir -p "$PROJECT_DIR/dist"
swiftc -O -emit-library \
  -module-name VlowGlass \
  -target arm64-apple-macosx26.0 \
  -o "$OUT" \
  "$PROJECT_DIR/native/VlowGlass.swift"

echo "Built $OUT"
