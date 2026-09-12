# vlow

Local voice dictation for macOS. Double-tap Right Option to toggle recording;
the transcript is pasted into whatever app currently has focus. Runs
on-device via MLX — Whisper `large-v3` or Parakeet TDT v3, your pick — with
no network and no API key; an AssemblyAI cloud backend is optional and the
only route with live streaming. Mixed German/English dictation is a design
goal: Parakeet and AssemblyAI handle it within a sentence, Whisper less so
(see [On-device models](#on-device-models)).

Apple Silicon only (MLX). Tested on macOS 26.

> The "no network" guarantee holds only for the default `mlx` backend. If you
> set `VLOW_BACKEND=auto` in your `.env`, every recording longer than
> `VLOW_AUTO_THRESHOLD_SEC` (default 60s) is uploaded to AssemblyAI — and
> ordinary dictation crosses a minute often, so that is a large share of them,
> not an occasional edge case. See [Transcription backends](#transcription-backends).

## Install

### Download the app

Grab the latest `vlow-<version>-arm64.dmg` from
[Releases](https://github.com/mcurses/vlow/releases), open it and drag
**vlow** into **Applications**. The bundle is self-contained (its own
Python, MLX, the glass overlay) — nothing else to install.

Or with Homebrew (same DMG, from the `mcurses/vlow` tap):

```bash
brew install --cask mcurses/vlow/vlow
# ad-hoc signed → either click "Open Anyway" once, or skip quarantine:
brew install --cask --no-quarantine mcurses/vlow/vlow
```

The cask is marked `auto_updates`, so `brew upgrade` leaves it alone and
vlow's own updater keeps it current; `brew upgrade --greedy` forces the
cask version.

- The build is ad-hoc signed, so on first launch macOS may say the app
  "cannot be verified". Open **System Settings → Privacy & Security**,
  scroll down and click **Open Anyway** (or run
  `xattr -dr com.apple.quarantine /Applications/vlow.app`).
- Grant **Microphone** and **Accessibility** when asked, then relaunch
  vlow (permission changes don't apply to a running process).
- On first launch vlow opens **Settings** and asks you to download an
  on-device model (one time, into `~/.cache/huggingface/hub/`): Whisper
  large-v3 (about 3 GB) or Parakeet TDT v3 (about 2.5 GB) — click
  **Download…** next to the one you want and watch the progress bar. If you
  only want the AssemblyAI cloud backend, skip it and enter your API key
  instead.
- Configure everything from the menubar icon → **Settings…** (⌘,): hotkey,
  mode, backend, on-device model, AssemblyAI key and known words. Changes
  apply immediately. Add vlow to *Login Items* if you want it to start
  with your Mac.
- **Updates:** menubar icon → **Check for Updates…**, or let the daily
  automatic check tell you. Installing an update downloads the new DMG,
  swaps the app in place and relaunches it. Because the build is ad-hoc
  signed, macOS asks for Accessibility again after each update.

Releases are produced by [`.github/workflows/release.yml`](.github/workflows/release.yml);
see [Building the DMG](#building-the-dmg) to build one yourself.

### From source

Requires [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`.

```bash
brew install ffmpeg            # for decoding audio formats other than wav
cd /path/to/vlow
uv sync
```

The model weights (`mlx-community/whisper-large-v3-mlx`, ~3 GB, and/or
`mlx-community/parakeet-tdt-0.6b-v3`, ~2.5 GB) are downloaded on request —
Settings → On-device model → Download — into `~/.cache/huggingface/hub/`;
vlow never fetches them silently. Unauthenticated
downloads are rate-limited; if it's slow, generate a token at
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
and write it to `~/.cache/huggingface/token` (mode 600).

## Transcription backends

| Backend       | Env                       | Notes                                                              |
|---------------|---------------------------|--------------------------------------------------------------------|
| `mlx` (default) | `VLOW_BACKEND=mlx`        | Local, offline, free. Apple Silicon only. Whisper or Parakeet, see below. |
| `assemblyai`  | `VLOW_BACKEND=assemblyai` | Cloud, paid, needs network. ~3–6s upload/queue overhead per call. |
| `auto`        | `VLOW_BACKEND=auto`       | Route by duration — short clips → `mlx`, long ones → `assemblyai`. |

### On-device models

Both run through MLX; pick one in **Settings → On-device model** (or
`local_model` in `config.toml` / `VLOW_LOCAL_MODEL`). Download either or both.

| `local_model`            | Weights                                  | Size   | Languages | Speed (M-series) | Mixed German/English |
|--------------------------|------------------------------------------|--------|-----------|------------------|----------------------|
| `whisper-large-v3` (default) | `mlx-community/whisper-large-v3-mlx` | ~3 GB  | 99        | ~6–10× realtime  | Weak: Whisper commits to one language per 30 s window, so English terms inside German speech get mangled or translated. Best for monolingual German. |
| `parakeet-tdt-0.6b-v3`   | `mlx-community/parakeet-tdt-0.6b-v3`     | ~2.5 GB | 25 (European incl. de/en) | ~25× realtime    | Good: no language token, transcribes what it hears. No prompt biasing, so known words are fixed up afterwards. |

For AssemblyAI (or `auto`), also set the API key — in **Settings…**, or as
`ASSEMBLYAI_API_KEY` in `.env` / `~/.config/vlow/.env`.
Language defaults to auto-detect, which on Universal-3.5 Pro also enables
mid-sentence code-switching across 18 languages; force one with
`VLOW_AAI_LANGUAGE=de` (any ISO 639-1 code). Speech models are
`["universal-3-5-pro", "universal-2"]` in fallback order; the hold gesture
streams through Universal-3.5 Pro Realtime.

For `auto` mode, the duration threshold is 60s by default. Change it
with `VLOW_AUTO_THRESHOLD_SEC=120` (env) or `auto_threshold_sec = 120`
in `~/.config/vlow/config.toml`. The menubar header shows the active
threshold while in auto mode.

The current backend appears in the menubar dropdown header; switch it in
**Settings…** — it applies without a relaunch.

## Settings

Menubar icon → **Settings…** (or ⌘, while the menu is open) opens a
System-Settings-style window (SwiftUI, `native/VlowSettings.swift`) for
the hotkey, mode, an optional re-paste shortcut (off by default; click **Record Shortcut** and press the keys), backend, auto threshold, the on-device model (picker
plus a download row per model with progress bar), AssemblyAI key and
language, the known-words list, and update checking. There is no Save button: every edit is written to
`~/.config/vlow/config.toml` and applied live — the hotkey monitor is
rebuilt, the backend re-warmed, known words are picked up by the next
recording.

If the selected on-device model is missing when it's needed, vlow shows the
warning icon, posts a notification and opens Settings instead of downloading
behind your back (`src/vlow/local_models.py`).

## Updates

Menubar icon → **Check for Updates…** asks the GitHub Releases API for
the latest tag (`src/vlow/updater.py`). A daily background check does the
same unless you turn it off in Settings → Updates. When a newer version
exists, *Install and Relaunch* does the whole thing with a progress bar in
Settings → Updates (and a percentage in the menubar item):

- **Downloaded app:** fetches the DMG, mounts it, swaps `vlow.app` in
  place (old copy kept until the new one is in position) and relaunches.
- **Source checkout** (`uv run vlow` or the launchd bundle from
  `vlow install`): `git pull --ff-only`, `uv sync`, rebuilds
  `dist/vlow.app` and restarts through launchd (or re-execs). Refuses to
  run on a dirty working tree or a detached HEAD.

On first launch vlow creates `config.toml` from whatever is in effect
(`.env` / environment) with one example known word, `vlow`.

## User config

`~/.config/vlow/config.toml` is the central config — the Settings window
writes it, but it's plain TOML you can also edit by hand. Keys set there
override `.env` and environment variables; keys left out fall back to
them.

```toml
hotkey = "fn"               # fn | right_opt | left_opt | right_cmd
mode = "toggle"             # toggle (default; double-tap + hold) or ptt (hold-only)
repaste_hotkey = ""         # e.g. "<ctrl>+<cmd>+v" (pynput spec) to re-paste the last transcript; empty = off
paste_to_origin_app = true  # batch: paste into the app that was in front when recording started
backend = "auto"            # mlx | assemblyai | auto  (ignored when mode = "ptt")
local_model = "whisper-large-v3"   # or parakeet-tdt-0.6b-v3 — the model behind "mlx"
auto_threshold_sec = 60     # used when backend = "auto"
assemblyai_api_key = "…"    # or ASSEMBLYAI_API_KEY in .env / the environment
aai_language = "de"         # empty / omitted → AssemblyAI auto-detects
known_words = ["EMMA Studio", "vlow"]   # bias all backends toward these names
check_updates = true        # daily GitHub Releases check
```

`known_words` is applied everywhere transcription happens:
- Whisper gets an `initial_prompt` (`"Words and names that may appear: …"`).
- Parakeet has no prompt; near-miss spellings in its output are replaced by
  the exact known word afterwards (`src/vlow/known_words_fix.py`, fuzzy
  match, conservative threshold).
- AssemblyAI pre-recorded gets `keyterms_prompt` *and* `word_boost` (the latter for the universal-2 fallback model) with `boost_param="high"`.
- AssemblyAI streaming gets `keyterms_prompt` in the `StreamingParameters`.

The list is re-read on every session start, so editing `config.toml`
takes effect without relaunching vlow.

## First launch

```bash
# Verify mic + model work (records 4 seconds, prints transcript)
.venv/bin/python -m vlow test

# Launch the menubar app
.venv/bin/python -m vlow
```

macOS will prompt for two permissions — both attach to the Python binary
running vlow, not to your terminal:

1. **Microphone** — auto-prompted on first record.
2. **Accessibility** — auto-prompted on launch via the system dialog.
   Required for the Right-Option monitor and the synthesized `Cmd+V`
   keystroke. After granting, **relaunch vlow** (permission changes
   don't apply to already-running processes).

## Usage

Two interaction modes, picked in `config.toml` via `mode = …`.

**`toggle` (default)** — one hotkey, two gestures:

| Gesture                        | Action                                       |
|--------------------------------|----------------------------------------------|
| Right Option × 2 (within 350 ms) | Start batch recording (mlx / assemblyai / auto). Double-tap again to stop and paste once. |
| Hold Right Option              | Live AssemblyAI streaming. Finalized turns paste into the focused app as they arrive. Release to stop. |
| Re-paste shortcut (Settings)   | Re-paste last transcript. Off until you record one. |

The hold gesture needs `ASSEMBLYAI_API_KEY`; without it, only double-tap
batch recording works (the startup notification will tell you).

Batch recordings remember the app that was in front when you double-tapped.
If you have switched to another app by the time the text is ready, vlow
brings the original app forward, pastes, and returns focus to where you
were (Settings → *Paste into the app I started in*, on by default;
streaming always pastes where you are).

**`ptt`** — hold-only streaming variant. No double-tap behavior; the
chosen modifier is dedicated to push-to-talk while vlow runs. Useful if
you don't want any double-tap dictation at all.

| Gesture                        | Action                                       |
|--------------------------------|----------------------------------------------|
| Hold Right Option              | Live AssemblyAI streaming with progressive paste. Release to stop. |
| Re-paste shortcut (Settings)   | Re-paste last transcript. Off until you record one. |

The menubar icon reflects state: mic idle, dimmed mic loading,
red mic recording, waveform transcribing, warning triangle error
(SF Symbol renders — regenerate with `scripts/gen-menubar-icons.py`). A small floating overlay also shows the
current state while you're recording.

If the hotkey misfires, use the menubar dropdown — it has reliable
fallbacks:

- `Stop & Transcribe` — same as the second double-tap
- `Discard Recording` — drop the current buffer, no paste
- `Re-paste Last` — same as the re-paste shortcut, works without one

## Input device

vlow follows the macOS system default input by default. PortAudio
caches its device list at import, so devices that connect *after* vlow
launched (e.g. a Bluetooth headset) would normally be invisible — we
re-scan on every recording start to compensate.

Menubar dropdown → `Input Device` lists every detected input,
including a system-default option and a `Refresh Devices` action for
when a device appears mid-session. Selecting a specific device pins it
for all subsequent sessions until you switch back to "Use System
Default" or quit the app (the choice is in-memory only — relaunch
returns to system default).

## Run as a background service (launchd)

Install a per-user LaunchAgent so vlow starts at every login and
restarts automatically if it crashes:

```bash
scripts/install-launchagent.sh
```

The script builds a minimal `dist/vlow.app` bundle, registers it with
launchd, and symlinks the `vlow` control CLI into `/opt/homebrew/bin`.
Two reasons for the bundle:

- macOS shows `vlow` in `System Settings → Privacy & Security →
  Accessibility` / `Microphone` instead of the raw `python3.12`
  binary. TCC attributes permissions to the *running process's
  executable*, so the bundle's `Contents/MacOS/vlow` is a copy of the
  venv's python binary (made venv-equivalent via `pyvenv.cfg` + a `lib`
  symlink) — a shell-script launcher would still show as `python3.12`.
- LSUIElement is set, so vlow doesn't take a Dock icon when launched
  via the bundle.

Logs land in standard macOS locations and are visible in Console.app
under "Log Reports":

- `~/Library/Logs/vlow/vlow.err` — startup phases (`[vlow HH:MM:SS] …`)
  and Python stderr.
- `~/Library/Logs/vlow/vlow.log` — MLX / AssemblyAI stdout.

```bash
vlow restart              # force-restart (picks up new code)
vlow stop / vlow start    # stop until next start/login · start again
vlow status               # launchd state + last log lines
vlow logs                 # live log tail (Ctrl-C to stop)
vlow install              # rebuild bundle + reinstall agent
scripts/uninstall-launchagent.sh   # remove agent (keeps logs)
```

(The `vlow` command is a symlink to `scripts/vlow`; the raw
`launchctl` equivalents are documented in that script.)

KeepAlive is set to restart only on `Crashed`, *not* on
`SuccessfulExit` — so clicking `Quit` from the menubar actually quits
until next login, while a crash is auto-recovered.

### First-time Accessibility under launchd

After the bundle executable changes (first install, or a rebuild that
replaces `Contents/MacOS/vlow`), macOS treats it as a new app and asks
to re-grant permissions:

1. `System Settings → Privacy & Security → Accessibility`
2. Find `vlow`, toggle it on (stale `python3.12` entries from the old
   launcher can be removed with the ⊖ button).
3. `vlow restart` to relaunch with the refreshed permission.
4. `vlow status` should now show `accessibility trusted=True` in the
   log tail. The Microphone prompt re-appears on the first recording.

## Recovery — last recording is always on disk

Every session — batch or streaming — writes its raw audio to
`~/Library/Application Support/vlow/last_recording.wav` before any
network round-trip. If MLX crashes, the WebSocket hangs, or you hit
"Discard" by mistake, the audio is still there. If vlow is terminated
mid-capture (`vlow restart`, `kill`, logout, an update relaunch), a
SIGTERM/SIGINT/SIGHUP hook writes whatever was recorded up to that
moment to the same file before the process exits (`src/vlow/diag.py`,
`install_termination_hook`). SIGKILL cannot be intercepted.

- **Reveal it** from the menubar dropdown → `Reveal Last Recording`,
  or open the file directly:
  ```bash
  open "$HOME/Library/Application Support/vlow/last_recording.wav"
  ```
- **Re-transcribe by hand** with any backend, e.g.:
  ```bash
  .venv/bin/python -c "
  import mlx_whisper
  r = mlx_whisper.transcribe(
      '$HOME/Library/Application Support/vlow/last_recording.wav',
      path_or_hf_repo='mlx-community/whisper-large-v3-mlx',
  )
  print(r['text'])
  "
  ```

Only the latest session is kept; each new recording overwrites the
previous file (written atomically: tmp + rename, so it's always either
the old valid recording or the new complete one).

## CLI

```bash
# One-shot record + transcribe to stdout (default 4 seconds)
.venv/bin/python -m vlow test
.venv/bin/python -m vlow test 8

# Run with hotkey diagnostics in stdout
VLOW_DEBUG=1 .venv/bin/python -m vlow
```

## Transcribing a file

`mlx-whisper` accepts any audio format ffmpeg can decode. Quick one-liner:

```bash
.venv/bin/python -c "
import mlx_whisper
r = mlx_whisper.transcribe(
    '/path/to/audio.m4a',
    path_or_hf_repo='mlx-community/whisper-large-v3-mlx',
    verbose=False,
)
print(r['text'])
"
```

Roughly 8–10× realtime on M-series for `large-v3`.

## Troubleshooting

- **Double-tap doesn't trigger anything.** Run with `VLOW_DEBUG=1`. If
  right-Option presses print to stdout but no callback fires, the gap
  is over the 350 ms threshold — tap faster or raise
  `threshold_sec` in `src/vlow/hotkey.py`. If presses don't print at
  all, Accessibility permission isn't actually active for the Python
  binary; re-check System Settings → Privacy & Security →
  Accessibility, toggle vlow's Python binary off and back on, then
  relaunch.
- **Stuck in "Recording" forever.** Use the `⏹ Stop & Transcribe`
  menubar item. If the menu is unresponsive, `Quit` and restart — the
  in-flight buffer is lost.
- **Empty transcript / "Thank you."** Whisper hallucinates that
  string on near-silent audio. Confirm your mic input is reaching the
  Recorder by running `.venv/bin/python -m vlow test` and watching the
  reported captured duration.
- **Paste produces nothing.** Some apps suppress synthesized `Cmd+V`.
  Falls back: the transcript is still in your clipboard — paste
  manually.
- **App is wedged: hotkey dead, menubar icon visible but clicking it
  does nothing.** Before restarting, capture diagnostics so the cause
  is findable afterwards:

  ```sh
  # 1. Dump all Python thread stacks into vlow.err
  kill -USR1 "$(pgrep -f -- '-m vlow')"

  # 2. Look at the trail: stack dump, heartbeat lines (every ~5 min:
  #    app state, status-item health, whether modifier-key events are
  #    still arriving), power events, state transitions
  tail -150 ~/Library/Logs/vlow/vlow.err

  # 3. Restart the service
  launchctl kickstart -k gui/$UID/com.vlow
  ```

  A watchdog thread also self-heals one variant of this: if the main
  runloop stops servicing pings for ~3 min while the app is idle, it
  dumps stacks and exits so launchd relaunches it.

## Building the DMG

```bash
scripts/build-release.sh              # → dist/release/vlow.app + dist/vlow-<version>-arm64.dmg
VLOW_SKIP_DMG=1 scripts/build-release.sh   # just the .app
```

The script downloads a relocatable CPython 3.12 (python-build-standalone,
via `uv python install`), installs the locked dependencies into it
(minus `torch`, which mlx-whisper declares but never imports at
runtime), compiles `native/launcher.c` — a tiny executable that embeds
libpython and runs `-m vlow`, so TCC sees `vlow` rather than `python` —
adds the icons and `libVlowGlass.dylib`, signs everything, runs an
import smoke test from inside the bundle, and wraps it in a DMG. About
90 s on an M-series Mac; the result is ~600 MB unpacked, ~240 MB as DMG.

Signing defaults to ad-hoc. For a Developer ID build set
`VLOW_SIGN_IDENTITY="Developer ID Application: …"` (adds hardened
runtime + `scripts/entitlements.plist`) and, to notarize, `VLOW_NOTARIZE=1`
with `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`.

CI does the same on `macos-26` runners: pushing a tag `v*` builds the DMG
and attaches it to a GitHub Release; *Run workflow* on the Actions tab
builds a downloadable artifact without releasing. Add the secrets listed
at the top of `.github/workflows/release.yml` to get signed, notarized
releases instead of ad-hoc ones.

```bash
git tag v0.1.3 && git push origin v0.1.3
```

## Layout

```
src/vlow/
├── __main__.py        CLI entry; `vlow` runs the app, `vlow test [secs]` one-shots
├── app.py             rumps.App, state machine, menubar items, permission prompt
├── audio.py           sounddevice InputStream → numpy float32 16 kHz mono (toggle mode)
├── transcribe.py      backend dispatcher (VLOW_BACKEND, VLOW_LOCAL_MODEL)
├── transcribe_mlx.py  local Whisper large-v3 via mlx-whisper
├── transcribe_parakeet.py  local Parakeet TDT 0.6B v3 via parakeet-mlx
├── known_words_fix.py fuzzy post-correction toward known words (Parakeet)
├── transcribe_aai.py  cloud universal-3.5-pro/2 via AssemblyAI SDK
├── stream_aai.py      live AssemblyAI Universal Streaming session (ptt mode)
├── hotkey.py          double-tap + hold detectors over NSEvent flagsChanged
├── overlay.py         borderless non-activating NSPanel hosting the SwiftUI
│                      glass pill (native/VlowGlass.swift → dist/libVlowGlass.dylib,
│                      compiled by scripts/build-glass.sh)
├── paste.py           pbcopy + synthesized Cmd+V via CGEvent
├── replay.py          pynput global Ctrl+Cmd+V → re-paste last text
├── resources.py       finds icons / dylib / .env in both the checkout and the .app
├── config.py          config.toml + .env loading, env mirroring
├── settings.py        settings schema, validation, TOML writer, first-run seeding
├── settings_window.py PyObjC bridge to the SwiftUI Settings window
├── local_models.py    on-device model registry, status + download with progress
└── updater.py         GitHub Releases check, DMG download, in-place swap, relaunch
native/
├── VlowGlass.swift    SwiftUI glass pill (→ libVlowGlass.dylib)
├── VlowSettings.swift SwiftUI Settings window (same dylib)
└── launcher.c         vlow.app main executable: embeds libpython, runs -m vlow
scripts/
├── build-release.sh   self-contained vlow.app + DMG (what CI ships)
├── build-app-bundle.sh  thin launchd wrapper around the local .venv
└── entitlements.plist hardened-runtime entitlements for signed builds
```
