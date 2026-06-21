# vlow

Local voice dictation for macOS. Double-tap Right Option to toggle recording;
the transcript is pasted into whatever app currently has focus. Uses
`mlx-whisper` with `large-v3` for on-device transcription — no network, no
API key, handles per-token German/English code-switching.

Apple Silicon only (MLX). Tested on macOS 26.

## Install

Requires [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`.

```bash
brew install ffmpeg            # for decoding audio formats other than wav
cd /path/to/vlow
uv sync
```

First run downloads the `mlx-community/whisper-large-v3-mlx` weights
(~3 GB) to `~/.cache/huggingface/hub/`. Unauthenticated downloads are
rate-limited; if it's slow, generate a token at
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
and write it to `~/.cache/huggingface/token` (mode 600).

## Transcription backends

| Backend       | Env                       | Notes                                                              |
|---------------|---------------------------|--------------------------------------------------------------------|
| `mlx` (default) | `VLOW_BACKEND=mlx`        | Local, offline, free. Apple Silicon only. ~8–10× realtime.        |
| `assemblyai`  | `VLOW_BACKEND=assemblyai` | Cloud, paid, needs network. ~3–6s upload/queue overhead per call. |
| `auto`        | `VLOW_BACKEND=auto`       | Route by duration — short clips → `mlx`, long ones → `assemblyai`. |

For AssemblyAI (or `auto`), also set `ASSEMBLYAI_API_KEY=<key>`.
Language defaults to auto-detect; force one with `VLOW_AAI_LANGUAGE=de`
(any ISO 639-1 code). Speech models are
`["universal-3-pro", "universal-2"]` in fallback order.

For `auto` mode, the duration threshold is 60s by default. Change it
with `VLOW_AUTO_THRESHOLD_SEC=120` (env) or `auto_threshold_sec = 120`
in `~/.config/vlow/config.toml`. The menubar header shows the active
threshold while in auto mode.

The current backend appears in the menubar dropdown header. To switch,
quit, change config, and relaunch.

## User config

Optional TOML file at `~/.config/vlow/config.toml`. All keys are
optional; env vars (and `.env`) override TOML.

```toml
hotkey = "fn"               # fn | right_opt | left_opt | right_cmd
mode = "toggle"             # toggle (default; double-tap + hold) or ptt (hold-only)
backend = "auto"            # mlx | assemblyai | auto  (ignored when mode = "ptt")
auto_threshold_sec = 60     # used when backend = "auto"
aai_language = "de"         # omit for AssemblyAI auto-detection
known_words = ["EMMA Studio", "vlow"]   # bias all backends toward these names
```

`known_words` is applied everywhere transcription happens:
- MLX gets a Whisper `initial_prompt` (`"Words and names that may appear: …"`).
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
| Ctrl + Cmd + V                 | Re-paste last transcript.                    |

The hold gesture needs `ASSEMBLYAI_API_KEY`; without it, only double-tap
batch recording works (the startup notification will tell you).

**`ptt`** — hold-only streaming variant. No double-tap behavior; the
chosen modifier is dedicated to push-to-talk while vlow runs. Useful if
you don't want any double-tap dictation at all.

| Gesture                        | Action                                       |
|--------------------------------|----------------------------------------------|
| Hold Right Option              | Live AssemblyAI streaming with progressive paste. Release to stop. |
| Ctrl + Cmd + V                 | Re-paste last transcript.                    |

The menubar icon reflects state: `🎙` idle, `🔴` recording,
`⏳` transcribing, `⚠️` error. A small floating overlay also shows the
current state while you're recording.

If the hotkey misfires, use the menubar dropdown — it has reliable
fallbacks:

- `⏹ Stop & Transcribe` — same as the second double-tap
- `✕ Discard Recording` — drop the current buffer, no paste
- `↻ Re-paste Last` — same as Ctrl+Cmd+V

## Input device

vlow follows the macOS system default input by default. PortAudio
caches its device list at import, so devices that connect *after* vlow
launched (e.g. a Bluetooth headset) would normally be invisible — we
re-scan on every recording start to compensate.

Menubar dropdown → `🎙 Input Device` lists every detected input,
including a system-default option and a `⟳ Refresh Devices` action for
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

The script builds a minimal `dist/vlow.app` bundle and registers it
with launchd. Two reasons for the bundle:

- macOS shows `vlow` in `System Settings → Privacy & Security →
  Accessibility` / `Microphone` instead of the raw `python3.12`
  binary. (CFBundleName lives in `dist/vlow.app/Contents/Info.plist`.)
- LSUIElement is set, so vlow doesn't take a Dock icon when launched
  via the bundle.

Logs land in standard macOS locations and are visible in Console.app
under "Log Reports":

- `~/Library/Logs/vlow/vlow.err` — startup phases (`[vlow HH:MM:SS] …`)
  and Python stderr.
- `~/Library/Logs/vlow/vlow.log` — MLX / AssemblyAI stdout.

```bash
tail -F ~/Library/Logs/vlow/vlow.err           # live log tail
launchctl print gui/$UID/com.vlow              # status
launchctl kickstart -k gui/$UID/com.vlow       # force-restart
scripts/uninstall-launchagent.sh               # remove agent (keeps logs)
```

KeepAlive is set to restart only on `Crashed`, *not* on
`SuccessfulExit` — so clicking `Quit` from the menubar actually quits
until next login, while a crash is auto-recovered.

### First-time Accessibility under launchd

When vlow runs as a LaunchAgent the underlying python binary is still
`/Users/max/.../.venv/bin/python`, even though the bundle is named
`vlow`. macOS may ask you to re-grant Accessibility the first time:

1. `System Settings → Privacy & Security → Accessibility`
2. Find `python3.12` (or `vlow` once the bundle is registered), toggle
   off then back on.
3. `launchctl kickstart -k gui/$UID/com.vlow` to restart with the
   refreshed permission.
4. `tail ~/Library/Logs/vlow/vlow.err` should now print
   `accessibility trusted=True`.

## Recovery — last recording is always on disk

Every session — batch or streaming — writes its raw audio to
`~/Library/Application Support/vlow/last_recording.wav` before any
network round-trip. If MLX crashes, the WebSocket hangs, or you hit
"Discard" by mistake, the audio is still there.

- **Reveal it** from the menubar dropdown → `📁 Reveal Last Recording`,
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

## Layout

```
src/vlow/
├── __main__.py        CLI entry; `vlow` runs the app, `vlow test [secs]` one-shots
├── app.py             rumps.App, state machine, menubar items, permission prompt
├── audio.py           sounddevice InputStream → numpy float32 16 kHz mono (toggle mode)
├── transcribe.py      backend dispatcher (VLOW_BACKEND)
├── transcribe_mlx.py  local large-v3 via mlx-whisper
├── transcribe_aai.py  cloud universal-3-pro/2 via AssemblyAI SDK
├── stream_aai.py      live AssemblyAI Universal Streaming session (ptt mode)
├── hotkey.py          double-tap + hold detectors over NSEvent flagsChanged
├── overlay.py         borderless non-activating NSPanel
├── paste.py           pbcopy + synthesized Cmd+V via CGEvent
└── replay.py          pynput global Ctrl+Cmd+V → re-paste last text
```
