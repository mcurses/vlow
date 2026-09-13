# Configuring vlow

Everything is in **Settings…** — menubar icon, or ⌘, while the menu is open.
It is a System-Settings-style window with no Save button: every edit is
written to `~/.config/vlow/config.toml` and applied live. The hotkey monitor
is rebuilt, the backend re-warmed, known words are picked up by the next
recording.

## Transcription backends

| Backend | Notes |
|---|---|
| **On-device (MLX)** — default | Local, offline, free. Apple Silicon only. Whisper or Parakeet, see below. |
| **AssemblyAI (cloud)** | Paid, needs network, needs a key. ~3–6 s upload/queue overhead per call. |
| **Auto — by duration** | Short clips stay on-device, long ones go to AssemblyAI. |

> **The "no network" guarantee holds only for the on-device backend.** In
> `auto` mode every recording longer than the threshold (60 s by default) is
> uploaded to AssemblyAI — and ordinary dictation crosses a minute often, so
> that is a large share of them, not an occasional edge case.

In auto mode the menubar header shows the active threshold. The current
backend always appears in the dropdown header and switches without a
relaunch.

## On-device models

Both run through MLX; pick one under **On-device model** and download either
or both. Weights land in `~/.cache/huggingface/hub/` and are only fetched
when you click **Download…** — vlow never pulls gigabytes in the background.
If the selected model is missing when it is needed, vlow shows the warning
icon, posts a notification and opens Settings.

| Model | Weights | Size | Languages | Speed | Mixed German/English |
|---|---|---|---|---|---|
| **Whisper large-v3** (default) | `mlx-community/whisper-large-v3-mlx` | ~3 GB | 99 | ~6–10× realtime | Weak. Whisper commits to one language per 30 s window, so English terms inside German speech get mangled or translated. Best for monolingual dictation. |
| **Parakeet TDT 0.6B v3** | `mlx-community/parakeet-tdt-0.6b-v3` | ~2.5 GB | 25 (European incl. de/en) | ~25× realtime | Good. No language token, so it transcribes what it hears. No prompt biasing, so known words are fixed up afterwards. |

Unauthenticated Hugging Face downloads are rate-limited. If it crawls,
generate a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
and write it to `~/.cache/huggingface/token` (mode 600).

## AssemblyAI

Needed for the hold-to-stream gesture and for the cloud and auto backends.
Set the key in Settings, or as `ASSEMBLYAI_API_KEY` in `.env` /
`~/.config/vlow/.env`.

Language defaults to auto-detect, which on Universal-3.5 Pro also enables
mid-sentence code-switching across 18 languages; force one with an ISO 639-1
code. Speech models are `["universal-3-5-pro", "universal-2"]` in fallback
order; the hold gesture streams through Universal-3.5 Pro Realtime.

## Known words

Names and terms every backend is nudged toward. The list is re-read on every
session start, so editing it takes effect without relaunching.

- **Whisper** gets an `initial_prompt` (`"Words and names that may appear: …"`).
- **Parakeet** has no prompt; near-miss spellings in its output are replaced
  by the exact known word afterwards (fuzzy match, conservative threshold —
  `src/vlow/known_words_fix.py`).
- **AssemblyAI pre-recorded** gets `keyterms_prompt` *and* `word_boost` (the
  latter for the universal-2 fallback) with `boost_param="high"`.
- **AssemblyAI streaming** gets `keyterms_prompt` in the `StreamingParameters`.

## Start at login

**Settings → Startup → Start vlow at login** writes a per-user LaunchAgent
(`~/Library/LaunchAgents/com.vlow.plist`). Besides starting vlow at login it
restarts it if it ever crashes — but not when you pick **Quit**, which quits
until the next login — and captures its output into `~/Library/Logs/vlow/`,
which is what the [troubleshooting steps](troubleshooting.md) read.

The change takes effect at your next login. vlow is already running when you
flip the switch, so it deliberately does not load the agent then and there;
that would put a second menubar icon on screen.

## Updates

**Check for Updates…** asks the GitHub Releases API for the latest tag; a
daily background check does the same unless you turn it off. When a newer
version exists, *Install and Relaunch* does the whole thing with a progress
bar in Settings (and a percentage in the menubar item):

- **Downloaded app** — fetches the DMG, mounts it, swaps `vlow.app` in place
  (the old copy is kept until the new one is in position) and relaunches.
  Because the build is ad-hoc signed, macOS asks for Accessibility again
  after each update.
- **Homebrew cask** — the cask is marked `auto_updates`, so `brew upgrade`
  leaves it alone and vlow's own updater keeps it current.
  `brew upgrade --greedy` forces the cask version instead.
- **Source checkout** — `git pull --ff-only`, `uv sync`, rebuild
  `dist/vlow.app`, restart through launchd or re-exec. Refuses to run on a
  dirty working tree or a detached HEAD.

## `config.toml` reference

`~/.config/vlow/config.toml` is the central config. The Settings window
writes it, but it is plain TOML you can edit by hand. Keys set there override
`.env` and environment variables; keys left out fall back to them. On first
launch vlow creates it from whatever is in effect, plus one example known
word.

```toml
hotkey = "fn"               # fn | right_opt | left_opt | right_cmd
mode = "toggle"             # toggle (double-tap + hold) or ptt (hold-only)
repaste_hotkey = ""         # e.g. "<ctrl>+<cmd>+v" (pynput spec); empty = off
paste_to_origin_app = true  # batch: paste into the app that was in front at start
return_focus_after_paste = true  # ... then switch back to the app you are in now
hold_to_stream = true       # toggle mode: hold to stream live; false = double-tap only
backend = "auto"            # mlx | assemblyai | auto  (ignored when mode = "ptt")
local_model = "whisper-large-v3"   # or parakeet-tdt-0.6b-v3 — the model behind "mlx"
auto_threshold_sec = 60     # used when backend = "auto"
assemblyai_api_key = "…"    # or ASSEMBLYAI_API_KEY in .env / the environment
aai_language = "de"         # empty / omitted → AssemblyAI auto-detects
known_words = ["EMMA Studio", "vlow"]   # bias all backends toward these names
check_updates = true        # daily GitHub Releases check
```

"Start at login" is not in this file — the LaunchAgent on disk is its single
source of truth, so the toggle always reflects what macOS will really do.

### Environment variables

Every key above that maps to one can also be set in the environment or in
`.env` (repo root for a checkout, `~/.config/vlow/.env` otherwise):
`ASSEMBLYAI_API_KEY`, `VLOW_BACKEND`, `VLOW_LOCAL_MODEL`,
`VLOW_AUTO_THRESHOLD_SEC`, `VLOW_AAI_LANGUAGE`. Plus `VLOW_DEBUG=1` for
hotkey diagnostics on stdout.
