# Development

## Running from source

Requires [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`.

```bash
brew install ffmpeg     # decoding audio formats other than wav
git clone https://github.com/mcurses/vlow && cd vlow
uv sync
uv run vlow             # menubar app
uv run vlow test        # 4s mic check
```

Model weights are downloaded on request from **Settings → On-device model →
Download**, into `~/.cache/huggingface/hub/`.

The SwiftUI parts (the glass overlay and the Settings window) compile to a
dylib that the checkout loads from `dist/`:

```bash
scripts/build-glass.sh  # → dist/libVlowGlass.dylib
```

### Running the checkout under launchd

Turning on **Start vlow at login** works from a checkout too, but by default
it registers the interpreter — so Privacy & Security says "python3.12" and
the Accessibility grant is attached to that binary. Building the thin app
bundle first makes macOS say "vlow" instead:

```bash
scripts/vlow install    # build dist/vlow.app, write the agent, start it now
scripts/vlow uninstall  # stop it and remove the agent
```

`scripts/build-app-bundle.sh` builds that bundle on its own. It is thin: the
bundle executable is a *copy of the venv's Python binary* (made
venv-equivalent by a `pyvenv.cfg` and a `lib` symlink), because TCC
attributes permissions to the running process's executable and a shell-script
launcher would still show as `python3.12`. It also sets `LSUIElement`, so no
Dock icon.

`src/vlow/login_item.py` is the only place that writes
`~/Library/LaunchAgents/com.vlow.plist`; the Settings toggle and
`scripts/vlow` both go through it.

## Building the DMG

```bash
scripts/build-release.sh                    # → dist/release/vlow.app + dist/vlow-<version>-arm64.dmg
VLOW_SKIP_DMG=1 scripts/build-release.sh    # just the .app
```

The script downloads a relocatable CPython 3.12 (python-build-standalone, via
`uv python install`), installs the locked dependencies into it (minus `torch`,
which mlx-whisper declares but never imports at runtime), compiles
`native/launcher.c` — a tiny executable that embeds libpython and runs
`-m vlow`, so TCC sees `vlow` rather than `python` — adds the icons and
`libVlowGlass.dylib`, signs everything, runs an import smoke test from inside
the bundle, and wraps it in a DMG. About 90 s on an M-series Mac; ~600 MB
unpacked, ~240 MB as a DMG.

Signing defaults to ad-hoc. For a Developer ID build set
`VLOW_SIGN_IDENTITY="Developer ID Application: …"` (which adds the hardened
runtime plus `scripts/entitlements.plist`) and, to notarize, `VLOW_NOTARIZE=1`
with `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`.

## Releasing

CI does the same on `macos-26` runners
([`.github/workflows/release.yml`](../.github/workflows/release.yml)). Pushing
a `v*` tag builds the DMG and attaches it to a GitHub Release; *Run workflow*
on the Actions tab builds a downloadable artifact without releasing. Add the
secrets listed at the top of the workflow to get signed, notarized releases
instead of ad-hoc ones.

```bash
git tag v0.1.4 && git push origin v0.1.4
```

## Layout

```
src/vlow/
├── __main__.py        CLI entry: the menubar app, `vlow test`, `vlow transcribe`
├── app.py             rumps.App, state machine, menubar items, permission prompt
├── audio.py           sounddevice InputStream → numpy float32 16 kHz mono; file decoding
├── transcribe.py      backend dispatcher (VLOW_BACKEND, VLOW_LOCAL_MODEL)
├── transcribe_mlx.py  local Whisper large-v3 via mlx-whisper
├── transcribe_parakeet.py  local Parakeet TDT 0.6B v3 via parakeet-mlx
├── known_words_fix.py fuzzy post-correction toward known words (Parakeet)
├── transcribe_aai.py  cloud universal-3.5-pro/2 via the AssemblyAI SDK
├── stream_aai.py      live AssemblyAI Universal Streaming session (hold gesture)
├── hotkey.py          double-tap + hold detectors over NSEvent flagsChanged
├── overlay.py         borderless non-activating NSPanel hosting the SwiftUI glass pill
├── paste.py           pbcopy + synthesized Cmd+V via CGEvent
├── replay.py          pynput global shortcut → re-paste last text
├── recordings.py      the always-on-disk last_recording.wav
├── resources.py       finds icons / dylib / .env in both the checkout and the .app
├── config.py          config.toml + .env loading, env mirroring
├── settings.py        settings schema, validation, TOML writer, first-run seeding
├── settings_window.py PyObjC bridge to the SwiftUI Settings window
├── login_item.py      the LaunchAgent behind "Start vlow at login"
├── local_models.py    on-device model registry, status + download with progress
├── diag.py            signal stack dumps, power logging, watchdog
└── updater.py         GitHub Releases check, DMG download, in-place swap, relaunch
native/
├── VlowGlass.swift    SwiftUI glass pill        ─┐
├── VlowSettings.swift SwiftUI Settings window   ─┴→ dist/libVlowGlass.dylib
└── launcher.c         vlow.app main executable: embeds libpython, runs -m vlow
scripts/
├── build-release.sh    self-contained vlow.app + DMG (what CI ships)
├── build-app-bundle.sh thin launchd wrapper around the local .venv
├── build-glass.sh      the SwiftUI modules → dist/libVlowGlass.dylib
├── gen-menubar-icons.py SF Symbol renders for the menubar states
├── vlow                launchd control CLI for a checkout
└── entitlements.plist  hardened-runtime entitlements for signed builds
```
