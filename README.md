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
backend = "auto"            # mlx | assemblyai | auto
auto_threshold_sec = 60     # used when backend = "auto"
aai_language = "de"         # omit for AssemblyAI auto-detection
```

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

| Action                         | Hotkey                                       |
|--------------------------------|----------------------------------------------|
| Start recording                | Right Option × 2 (within 350 ms)             |
| Stop and paste                 | Right Option × 2 again                       |
| Re-paste last transcript       | Ctrl + Cmd + V                               |

The menubar icon reflects state: `🎙` idle, `🔴` recording,
`⏳` transcribing, `⚠️` error. A small floating overlay also shows the
current state while you're recording.

If the hotkey misfires, use the menubar dropdown — it has reliable
fallbacks:

- `⏹ Stop & Transcribe` — same as the second double-tap
- `✕ Discard Recording` — drop the current buffer, no paste
- `↻ Re-paste Last` — same as Ctrl+Cmd+V

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
├── audio.py           sounddevice InputStream → numpy float32 16 kHz mono
├── transcribe.py      backend dispatcher (VLOW_BACKEND)
├── transcribe_mlx.py  local large-v3 via mlx-whisper
├── transcribe_aai.py  cloud universal-3-pro/2 via AssemblyAI SDK
├── hotkey.py          global + local NSEvent flagsChanged → double-tap detector
├── overlay.py         borderless non-activating NSPanel
├── paste.py           pbcopy + synthesized Cmd+V via CGEvent
└── replay.py          pynput global Ctrl+Cmd+V → re-paste last text
```
