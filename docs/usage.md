# Using vlow

vlow lives in the menubar. Everything below assumes it is running and that
you have granted **Microphone** and **Accessibility** (see
[Troubleshooting](troubleshooting.md#permissions) if a gesture does nothing).

## Gestures

Two interaction modes, picked in **Settings → Mode**. The hotkey is Fn by
default; Right Option, Left Option and Right Command are the alternatives.

### `toggle` (default) — one hotkey, two gestures

| Gesture | Action |
|---|---|
| Hotkey × 2 (within 350 ms) | Start recording. Double-tap again to stop; the recording is queued, transcribed and pasted once. |
| Hold the hotkey | Live AssemblyAI streaming. Finalized turns paste into the focused app as they arrive. Release to stop. |
| Re-paste shortcut | Paste the last transcript again. Off until you set one in Settings. |

The hold gesture needs an AssemblyAI API key; without one, only the
double-tap works (the startup notification says so). If you never want it,
turn off **Hold to stream live** — the hotkey then only reacts to
double-taps.

### Recording while something is still transcribing

You don't have to wait for a transcription to come back. Stopping a
recording only queues it, so the next double-tap starts recording straight
away. The overlay shows one glass blob per queued transcription, budding out
of the left of the recording pill; each blob dissolves when its text lands.

Transcriptions of long recordings routed to AssemblyAI run in parallel, while
on-device ones run one at a time (MLX inference is single-threaded).

**Text always arrives in the order you spoke it — per app.** A transcription
waits for older ones headed to the *same* app, but never for one going
somewhere else. So a quick note dictated into Slack is not held up by the
five-minute recording still uploading for Notes, while two recordings for
Slack always paste in the order you made them.

### `ptt` — hold-only

No double-tap behaviour at all; the chosen modifier is dedicated to
push-to-talk streaming while vlow runs.

| Gesture | Action |
|---|---|
| Hold the hotkey | Live AssemblyAI streaming with progressive paste. Release to stop. |
| Re-paste shortcut | Paste the last transcript again. |

## Where the text lands

Batch recordings remember the app that was in front when you double-tapped.
If you have switched elsewhere by the time the text is ready, vlow brings the
original app forward, pastes, and returns focus to where you are now — both
halves are toggles in Settings (*Paste into the app I started in*, *Return to
where I was afterwards*), on by default.

Streaming always pastes into whatever is focused right now, because the text
arrives while you are still talking.

vlow never pastes into itself.

## Menubar

The icon reflects state: mic idle, dimmed mic loading, red mic recording,
waveform transcribing, warning triangle error. A small floating overlay also
shows the current state while you record.

If the hotkey misfires, the dropdown has reliable fallbacks:

- **Stop & Transcribe** — same as the second double-tap (queues the recording)
- **Discard Recording** — drop the buffer, no paste
- **Re-paste Last** — works even without a re-paste shortcut configured
- **Reveal Last Recording** — opens the raw audio in Finder
- **Input Device** — see below

## Input device

vlow follows the macOS system default input. PortAudio caches its device list
at import, so a headset that connects *after* vlow launched would normally be
invisible; vlow re-scans on every recording start to compensate.

The **Input Device** submenu lists every detected input plus a **Refresh
Devices** action. Pinning a specific device holds for all later sessions
until you switch back to *Use System Default* or quit — the choice is
in-memory only, so a relaunch returns to the system default.

## Command line

The `vlow` command runs the menubar app when given no arguments. From a
source checkout use `uv run vlow`; the installed app's executable works too
(`/Applications/vlow.app/Contents/MacOS/vlow`).

```bash
vlow                      # run the menubar app
vlow test                 # record 4s from the mic, print the transcript
vlow test 8               # ... for 8 seconds
vlow transcribe talk.m4a  # transcribe a file to stdout
```

`vlow transcribe` takes any format ffmpeg can decode, including the audio
track of a video, and several files at once:

```bash
vlow transcribe interview.m4a > interview.txt
vlow transcribe -o notes.md day1.wav day2.wav
vlow transcribe --backend assemblyai long-meeting.mp3
vlow transcribe --model parakeet-tdt-0.6b-v3 mixed-language.m4a
```

It goes through the same backend, the same model and the same known-words
biasing as dictation does; `--backend` and `--model` override the
configuration for that one run without touching `config.toml`. Transcripts
go to stdout and progress to stderr, so piping gives you the text alone.

Set `VLOW_DEBUG=1` to print hotkey diagnostics while the app runs.

## Recovery — the last recording is always on disk

Every session, batch or streaming, writes its raw audio to
`~/Library/Application Support/vlow/last_recording.wav` *before* any network
round-trip. If MLX crashes, the WebSocket hangs, or you hit Discard by
mistake, the audio is still there. If vlow is terminated mid-capture (a
restart, `kill`, logout, an update relaunch), a SIGTERM/SIGINT/SIGHUP hook
writes whatever was captured up to that moment before the process exits.
SIGKILL cannot be intercepted.

That file only ever holds the newest recording — each one overwrites the
last, written atomically, so it is always either the old valid recording or
the new complete one. Because a queue can hold several recordings at once,
each queued one *also* gets its own file in
`~/Library/Application Support/vlow/pending/`, kept until its text has been
pasted, so a crash with three jobs in flight can't lose the older two.

```bash
# Reveal it (or use the menubar item)
open "$HOME/Library/Application Support/vlow/last_recording.wav"

# Transcribe it again, with any backend
vlow transcribe "$HOME/Library/Application Support/vlow/last_recording.wav"
```
