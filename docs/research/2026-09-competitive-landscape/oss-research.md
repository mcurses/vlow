# Open-source macOS dictation apps: competitive research

Research date: **2026-09-11**. All star counts, licenses, languages, push dates and release
metadata were read from the GitHub REST API on that date. READMEs and source files were fetched
from the repositories themselves, not from search snippets. Homebrew cask presence was verified
against `formulae.brew.sh/api/cask/<token>.json`.

Scope: system-wide voice dictation for macOS with a hotkey-speak-paste-at-cursor loop. Two
high-star projects surfaced by search are **excluded** because they are not macOS apps:
`peteonrails/voxtype` (1,443 stars, Wayland/Linux only) and `goodroot/hyprwhspr` (1,195 stars,
Linux only).

---

## 1. Identity and distribution

| App | Stars | License | Written in | Platforms | Last release | macOS artifact size |
|---|---|---|---|---|---|---|
| [Handy](https://github.com/cjpais/Handy) | 31,379 | MIT | Rust + Tauri 2 (React/TS UI) | macOS (Intel + AS), Windows x64, Linux x64 | v0.9.6, 2026-08-24 | 18 MB DMG |
| [FluidVoice](https://github.com/altic-dev/FluidVoice) | 11,438 | GPL-3.0 (Apache-2.0 before 2026-02-23) | Swift | macOS 15+, iOS/Windows waitlisted | v1.6.9, 2026-08-18 | 47 MB DMG |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | 8,052 | MIT | TypeScript + Electron 41 | macOS, Windows, Linux | v1.10.0, 2026-09-11 | 317 MB DMG |
| [VoiceInk](https://github.com/Beingpax/VoiceInk) | 6,388 | GPL-3.0 (see note) | Swift | macOS 14.4+ | v2.13, 2026-08-27 | 47 MB DMG |
| [Whispering](https://github.com/EpicenterHQ/epicenter/tree/main/apps/whispering) | 4,797 (monorepo) | unverified | TypeScript, SvelteKit + Tauri | browser SPA + Epicenter desktop | rolling, pushed 2026-09-08 | n/a |
| [OpenLess](https://github.com/Open-Less/openless) | 3,498 | AGPL-3.0 | Rust + Tauri 2 | macOS 12+, Windows 10+, Android; Linux (egui) unreleased | active daily | not measured |
| [Hex, legacy Swift](https://github.com/kitlangton/Hex) | 2,895 | MIT | Swift (TCA) | macOS, Apple Silicon only | v0.8.5, 2026-08-27 | 14 MB DMG |
| [Hex, Rust rewrite](https://github.com/anomalyco/hex) | 183 | MIT | Rust (GPUI) | macOS 15+ AS, Linux beta | 2026-09-05 | not measured |
| [OpenSuperWhisper](https://github.com/Starmel/OpenSuperWhisper) | 2,861 | MIT | Swift | macOS ARM64 | 0.1.0, 2026-03-03 | 11 MB DMG |
| [TypeWhisper](https://github.com/TypeWhisper/typewhisper-mac) | 1,779 | GPL-3.0 | Swift 6 | macOS 14+ | v1.7.0-rc1, 2026-09-10 | 13 MB DMG |
| [Amical](https://github.com/amicalhq/amical) | 1,526 | MIT | TypeScript + Electron | macOS, Windows, Android; iOS beta | v1.12.0-beta.5, 2026-09-05 | 189 MB DMG (arm64) |
| [Muesli](https://github.com/Muesli-HQ/muesli) | 1,206 | MIT | Swift | macOS, Apple Silicon | v0.8.4, 2026-09-09 | 98 MB DMG |
| [whisper-writer](https://github.com/savbell/whisper-writer) | 1,100 | GPL-3.0 | Python + PyQt5 | macOS, Windows, Linux | dormant, last push 2024-08-24 | source only |
| [Voquill](https://github.com/voquill/voquill) | 1,008 | AGPL-3.0 | TypeScript + Tauri | macOS, Windows, Linux | pushed 2026-08-01 | not measured |
| [MiniWhisper](https://github.com/andyhtran/MiniWhisper) | 33 | MIT | Swift 6 | macOS 14+ | pushed 2026-08-16 | not measured |
| [WhisperDictation](https://github.com/sam-pop/WhisperDictation) | 8 | MIT | Swift | macOS | pushed 2026-09-02 | not measured |
| [Blurt](https://github.com/AssemblyAI/blurt) | 5 | MIT | Swift 6, AppKit + SwiftUI | macOS 15+, Apple Silicon | v0.1.53, 2026-09-11 | 6 MB DMG |

### Distribution channels

| App | Signed / notarized | Homebrew | In-app updater | Other |
|---|---|---|---|---|
| Handy | **Yes, verified in CI.** `build.yml` imports a Developer ID Application cert and passes `APPLE_ID`, `APPLE_ID_PASSWORD`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` to `tauri-apps/tauri-action@v0`, which notarizes. Windows signed via Azure Trusted Signing. | core cask `handy` | Tauri updater, minisign-verifiable artifacts (`createUpdaterArtifacts: true`) | winget `cjpais.Handy`, Raycast extension, CLI flags, Unix signals |
| FluidVoice | Inferred yes. No release workflow in repo (DMGs built locally), but core cask has no Gatekeeper caveat. | core cask `fluidvoice` | Sparkle, with opt-in beta channel | GitHub Sponsors |
| OpenWhispr | not verified | core cask `openwhispr` | electron-updater (`latest-mac.yml` in release assets) | docs site, public API, MCP server |
| VoiceInk | Inferred yes. Core cask, no caveat. | core cask `voiceink` | **Sparkle** (listed in README deps) | paid licence gates updates |
| Whispering | n/a browser; desktop via Epicenter | no | not verified | hosted SPA at whispering.epicenter.so |
| OpenLess | **No. Explicitly ad-hoc signed, not Apple-notarized.** README instructs users to clear the quarantine flag by hand. | own tap `Open-Less/openless` | Tauri updater (`TAURI_SIGNING_PRIVATE_KEY`) | Windows installer; Linux held back |
| Hex (Rust) | Yes, "signed DMG" + built-in updater per README | tap `anomalyco/tap/hex` | built-in, "Check for Updates..." | TypeScript SDK on npm; GitHub releases hold the SDK, not the app |
| Hex (Swift) | not verified | core cask `kitlangton-hex` | Sparkle (release script feeds the appcast) | S3-hosted DMG |
| OpenSuperWhisper | not verified | core cask `opensuperwhisper` | not verified | — |
| TypeWhisper | Inferred yes; "distributed-build entitlements" mentioned | tap `typewhisper/tap/typewhisper` | **Sparkle** with stable / RC / daily channels | plugin marketplace, backup+restore |
| Amical | not verified | core cask `amical` | not verified | Google Play, iOS beta |
| Muesli | README says "Developer ID + hardened runtime (notarization ready)" — **not the same as notarized** | core cask `muesli` | not verified | `muesli-cli` for coding agents, Apple Shortcuts + Siri |
| Blurt | **Yes, README states "Signed & notarized"** | no | **Deliberately not.** Checks once a day, offers to open the DMG, never replaces itself. | AssemblyAI-hosted landing page |
| MiniWhisper | Release recipes include `sign-and-notarize` via `asc` | own tap `andyhtran/tap` | not verified | — |
| WhisperDictation | **No. README: "The app is not notarized by Apple."** | no | not verified | — |
| whisper-writer | n/a, run from source | no | no | — |
| Voquill | not verified | no | Tauri auto-updates per README | enterprise services in repo |

---

## 2. Capability matrix

`Y` = explicitly documented or found in source. `N` = documented as absent or nothing found.

| App | Local STT engines | large-v3 | Cloud STT / BYOK | Custom vocabulary | Live streaming | Overlay | Price |
|---|---|---|---|---|---|---|---|
| Handy | whisper.cpp/GGML + GGUF via `transcribe-cpp`; Parakeet v2/v3 int8 via `transcribe-rs`; Parakeet Unified EN 0.6B GGUF | **Y** (`ggml-large-v3-q5_0` 1.1 GB, `ggml-large-v3-turbo` 1.6 GB) | Post-process LLM providers are BYOK and OpenAI-compatible, incl. Apple Intelligence. No cloud STT. | **Y, dual path**: native decode prompt where the model accepts it, plus ASCII-only fuzzy correction | **Y**, gated on model capability, independent of overlay setting | pill (Minimal) or growing transcript panel (Live); `None` default on Linux | free |
| FluidVoice | Nemotron Speech 3.5 (ultra-low-latency + multilingual), Parakeet Flash beta, Parakeet TDT v3/v2, Cohere Transcribe, Apple Speech, Whisper tiny→large | **Y** (Whisper family up to ~2.9 GB) | **Y** OpenAI, Groq, custom provider; keys in Keychain | **Y** `CustomDictionaryView`, `PronunciationDictionaryStore`, `AutomaticDictionaryTrainingSession` | **Y**, "Live Preview" real-time overlay | **notch-aware**, sizes from pill to large | free; GitHub Sponsors |
| OpenWhispr | whisper.cpp (Metal/CUDA/Vulkan), Parakeet via sherpa-onnx, Cohere Transcribe, "Orukeet", llama.cpp for LLM | not confirmed | **Y** GPT-5, Claude, Gemini, Groq, Tinfoil, OpenRouter + Bedrock/Azure for enterprise | not confirmed | not confirmed for dictation; live diarization for meetings | floating panel | free app; paid cloud + enterprise tiers |
| VoiceInk | whisper.cpp (`LibWhisper`), transcribe.cpp GGUF, Parakeet v2/v3/Unified + Nemotron Latin/Multilingual via FluidAudio, Cohere Transcribe, SenseVoice Small, Apple Speech (macOS 26) | **Y** (`ggml-large-v3`, `-v3-turbo`, `-v3-turbo-q5_0`, `large-v2`) | **Y, 10 providers**: Groq, ElevenLabs, Deepgram, Mistral, Gemini, Soniox, Speechmatics, AssemblyAI, xAI, Cartesia | **Y** Personal Dictionary + Smart Replace; `customVocabulary: [String]` is a first-class param on the `CloudProvider` protocol | **Y** `makeStreamingProvider` + `isStreamingOnly` on the provider protocol; Parakeet Unified has "native realtime transcription support" | recorder UI, mini recorder | **$25 / $39 / $49 one-time** |
| Whispering | GGUF on desktop only, none in browser | not confirmed | **Y**: `epicenter` gateway, OpenAI, Groq, ElevenLabs, Deepgram, Mistral, `speaches` self-hosted, or a self-hosted endpoint | **Y** via Whisper prompt (`supportsPrompt` capability flag) | **N** | in-page (browser) / native auxiliary window (desktop) | free |
| OpenLess | bundled Qwen3-ASR 0.6B / 1.7B (macOS, vendored `Open-Less/qwen-asr`); Windows Foundry Local Whisper + sherpa-onnx experimental | **N** | **Y, a dozen plus**: Volcengine, Tencent Hunyuan, iFlytek RTASR, Alibaba Bailian, StepFun, Zhipu GLM-ASR, Xiaomi MiMo, ElevenLabs Scribe, OpenAI-compatible, Apple Speech. Polish via Ark, DeepSeek, OpenAI, Gemini, OpenRouter and more | **Y, real ASR hotwords**: Volcengine `context.hotwords`, StepFun `hotwords`, Whisper `prompt`, Bailian vocabulary ID; finite budget ranked by hit count; **learns from your manual corrections** with a confirm card | **Y, character-by-character streaming insertion**, auto-falls back to one-shot paste | menu bar; Home/History/Dictionary/Settings window | free |
| Hex (Rust) | local model downloaded at setup (Parakeet/Whisper lineage from the Swift app) | not confirmed | optional, via OpenCode V2 beta for post-processing and Voice Action | **Y** "Corrections in Modes fix names and preferred spellings before text is pasted" | not documented | menu bar hexagon | free |
| Hex (Swift) | Parakeet TDT v3 via FluidAudio; WhisperKit | not confirmed | N | N | N | menu bar | free |
| OpenSuperWhisper | whisper.cpp; Parakeet via FluidAudio | **Y** plus an ivrit.ai Hebrew fine-tune of large-v3-turbo | **N** | **N — open TODO (#19)** | **N — open TODO** | indicator window | free |
| TypeWhisper | WhisperKit, Parakeet TDT v3, Apple SpeechAnalyzer, Granite Speech, Qwen3 ASR, Voxtral, Cohere Transcribe (local) | **Y** (docs show "German language, Whisper Large v3") | **Y** Groq Whisper, OpenAI, Soniox, Smallest Pulse, xAI/Grok, OpenAI-compatible profiles | **Y** Dictionary with terms + auto-learned corrections + **importable term packs**, localized EN/DE | **Y** "Streaming preview... partial transcription in real-time while speaking (WhisperKit)"; Soniox live | **notch / overlay / minimal**, optional live transcript | free core + **paid Premium** (calendar automation, correction learning, cloud folder sync) |
| Amical | whisper.cpp submodule (native addon), Ollama for local LLM | not confirmed | optional cloud, keys in `.env` | not confirmed | not confirmed | floating widget | free |
| Muesli | Apple Speech (SpeechAnalyzer), Parakeet TDT/Unified/Realtime EOU, Nemotron 3.5, Cohere Transcribe 2B CoreML, WhisperKit tiny/small/large-turbo, Qwen3 ASR, SenseVoice Small, Bodhan, Gemma 4 E2B | **Y** Whisper Large Turbo | **Y** OpenAI (Realtime WebSocket), OpenRouter model of choice; Ollama/ChatGPT subscription for notes | **Y** personal dictionary with phrase matches, replacement pairs and **Jaro-Winkler fuzzy matching**; JSON import/export | **Y for meetings** (Nemotron 3.5, Apple Speech, Parakeet Realtime EOU); dictation is hold-release | **frosted glass pill** with dynamic waveform, accent colour, click-to-stop | free |
| whisper-writer | faster-whisper (CTranslate2), CUDA optional | Y via `local.model` choice | OpenAI API or any compatible `base_url` (LocalAI etc.) | **Y** `initial_prompt` config key | continuous recording mode | small status window | free |
| Voquill | Whisper local, optional GPU | not confirmed | **Y** BYOK, choose transcription + post-processing provider | **Y** glossary terms + replacement rules | not confirmed | overlay | free |
| MiniWhisper | Parakeet via FluidAudio (EN + 20 European), whisper.cpp multilingual auto-detect | not confirmed | **N** | text replacements applied **after** transcription only | **N** | menu bar popover | free |
| WhisperDictation | whisper.cpp static lib, Metal GPU (`GGML_METAL=ON`) | **N** — Base 142 MB / Small 466 MB / Medium 1.5 GB only | **N**, zero network except model download | **Y**, 500+ built-in technical terms as a Whisper prompt, user-editable | **Y, commit-on-pause**: each phrase typed ~0.5 s after you pause, never revises already-typed text. Needs Silero VAD (2 MB). Off by default. | HUD | free |
| Blurt | **none, cloud-only** | **N** | AssemblyAI only, **BYOK required** (free tier exists) | **Y** key terms sent as the `keyterms-prompt` list to bias spelling | **N**, one POST per utterance | **floating pill** with live mic level meter + phase, mirrored in menu bar | free app, you pay AssemblyAI |

---

## 3. Hotkey gestures

| App | Gestures |
|---|---|
| Handy | hold-to-record + release, or tap-to-toggle; hold-only and toggle-only modes; `hold_threshold_ms` default 300 ms. **fn/Globe key works only on Apple keyboards** (vendor-specific HID usage) — documented hardware limitation, and Globe-key support is on the roadmap. |
| FluidVoice | configurable global hotkey |
| VoiceInk | keyboard **or mouse** shortcuts, push-to-talk |
| Hex | hold Option → release; **double-tap Option to latch**; Escape to cancel; Option-Shift-V repastes last dictation; Option-Command for Voice Action |
| OpenSuperWhisper | key combination, **single modifier** (Left ⌘, Right ⌥, Fn), **middle/thumb mouse button**, hold-to-record |
| TypeWhisper | push-to-talk, toggle, or **hybrid**; single modifier (Cmd/Shift/Option/Control) |
| Muesli | any modifier (Cmd, Option, Ctrl, **Fn**, Shift); hold-to-talk or **double-tap for hands-free latch**; also Siri and Apple Shortcuts |
| Blurt | **lone modifier only, no chords** — right ⌘ default, right ⌥ available; tap to toggle, hold for push-to-talk; combos like ⌘C pass through untouched |
| MiniWhisper | Option+W toggle default, rebindable including **Fn**; Escape cancels |
| WhisperDictation | right Option default; push-to-talk **or** toggle with a configurable 1.5 s hold to prevent accidental activation (explicitly framed as RSI/carpal-tunnel friendly) |
| OpenLess | single global hotkey, hold to speak; hotkey also switches the active style pack |
| Handy (headless) | CLI `--toggle-transcription`, `--toggle-post-process`, `--cancel`; `pkill -USR2` on Linux |

---

## 4. Multilingual and code-switching

This is the weakest-covered axis in the field and a plausible wedge.

- **Blurt is the only app that states intra-utterance code-switching outright**: "works in 18
  languages, detected automatically, and you can code-switch mid-sentence."
- **TypeWhisper** ships a documented German dictation workflow on Whisper Large v3 and a
  German-to-English translating workflow, plus a localized German UI and German-localized
  dictionary term packs. It does not claim mixed-language utterances.
- **FluidVoice** offers Nemotron Speech 3.5 across ~40 languages and Parakeet TDT v3 across 25
  (German included). No code-switching claim.
- **Handy** relies on Parakeet V3's automatic language detection, so no manual language selection
  is needed, but nothing is said about mixed-language input. It also has a `translate_to_english`
  setting and a `selected_language` setting, implying one language per utterance.
- **Muesli** offers Apple Speech (system locales), multilingual Whisper and Nemotron 3.5. No
  code-switching claim.
- **VoiceInk** covers German through whisper large-v3, Parakeet v3, Nemotron Multilingual,
  SenseVoice and Cohere Transcribe. No code-switching claim.
- **OpenLess** is explicit about Chinese homophone disambiguation via cursor context, which is the
  same class of problem solved differently: feed the polish LLM surrounding text so it can fix
  what the acoustic model cannot distinguish. That approach would transfer directly to
  German/English mixing.

---

## 5. AI post-processing and "platform-iness"

Ranked by how far past "dictate and paste" each has travelled.

1. **OpenWhispr** — dictation, dictation-translation hotkey, AI agent with a named voice
   assistant, meeting transcription with diarization and voice fingerprinting, calendar
   integration, notes with semantic search and cloud sync, team spaces and web sharing, audio and
   YouTube import, enterprise SSO/SCIM, public API, MCP server.
2. **TypeWhisper** — Workflows (reusable transformations triggered per-app, per-website,
   app+website, hotkey, global fallback or palette), ordered LLM provider fallbacks across Apple
   Intelligence / Groq / OpenAI / Grok / Gemini, local Gemma 4 via MLX, Apple Translate,
   TTS readback, a plugin marketplace with an MCP Client action, Obsidian live sync, Recorder
   API, SRT/WebVTT export, paid Premium tier.
3. **Muesli** — dictation plus Granola-style meetings, local diarization, Quill voice
   writing/rewriting, iCloud text sync and an iPhone bridge, six Apple Shortcuts actions, Siri,
   Computer Use, and `muesli-cli` explicitly designed for Codex and Claude Code to read
   dictations and write notes back.
4. **FluidVoice** — Command Mode (voice control of the Mac: launch apps, run shortcuts, automate),
   Write Mode (rewrite selected text in place), per-app prompt sets, and **Fluid Intelligence**,
   a fully local AI enhancement runtime that the maintainers keep **private and closed** while the
   app itself stays GPL-3.0. The repo alone will not build the full product.
5. **Hex (Rust)** — Modes with corrections and optional rewriting, Voice Action, experimental
   continuous local voice commands with user-authored TypeScript in `~/.config/hex/hex.config.ts`,
   a published TypeScript SDK, and an installable agent skill
   (`npx skills add anomalyco/hex --skill hex-personal-commands`).
6. **VoiceInk** — Modes with automatic app/URL detection, screen-context awareness, AI Assistant
   conversational mode, Smart Replace.
7. **OpenLess** — style packs with custom system prompts, AI-prompt mode that turns loose speech
   into a structured LLM prompt, cursor context, learning dictionary.
8. **Amical** — context-aware formatting per active app, voice macros, planned MCP integration
   and meeting transcription.
9. **Handy** — post-process toggle with provider records, API keys, multiple named LLM prompts,
   Apple Intelligence as a provider, filler-word removal with a custom filler list, auto-submit
   with a configurable key. Deliberately stays a utility: "One tool, one job."
10. **Blurt** — server-side LLM cleanup folded into the same single request as transcription. No
    modes, no local models, no post-processing UI.
11. **WhisperDictation** — rule-based local corrector under 5 ms, optional grammar correction.
12. **MiniWhisper** / **OpenSuperWhisper** / **whisper-writer** — plain transcription plus text
    replacement or autocorrect.

---

## 6. Per-app deep notes

### Handy — the giant and the reference implementation
`cjpais/Handy`, 31,379 stars, MIT, Rust + Tauri. Created 2025-02-13, pushed today.
Positioning is unusual and worth copying: *"Handy isn't trying to be the best speech-to-text
app — it's trying to be the most forkable one."*

- **Custom vocabulary is implemented twice.** `src-tauri/src/settings.rs` holds
  `custom_words: Vec<String>` and `word_correction_threshold: f64`. Words are passed as native
  decode prompts to models that accept them. On top of that,
  `src-tauri/src/audio_toolkit/text.rs` runs a fuzzy fallback: it builds n-grams by stripping
  punctuation and concatenating words (so "Charge B" matches "ChargeBee") and scores with
  `strsim::levenshtein` plus `natural::phonetics::soundex`. The fallback is **deliberately
  ASCII-only** and skips CJK, which means German umlauts also fall through to the prompt path.
- **Streaming is decoupled from the overlay.** `OverlayStyle` is `None | Minimal | Live`, and the
  doc comment says streaming mode "is driven purely by model capability", with
  `src-tauri/src/managers/model_capabilities.rs` doing the gating.
- **Post-processing is a real subsystem**: `PostProcessProvider` records with editable base URLs
  and model endpoints, `LLMPrompt` list with a selected prompt id, a `SecretMap` of API keys, and
  `APPLE_INTELLIGENCE_PROVIDER_ID` as a built-in provider.
- Other notable settings: `paste_method`, `clipboard_handling`, `reliable_paste` (clipboard-read
  receipts instead of a fixed restore delay), `typing_tool`, `external_script_path`,
  `filler_word_removal_enabled` + `custom_filler_words`, `auto_submit` + `auto_submit_key`,
  `mute_while_recording`, `recording_retention_period`, `vad_backend`.
- **Honest known-issues section** covering Bluetooth mic degradation on macOS, the fn/Globe
  Apple-keyboards-only limitation, Whisper crashes on some Windows/Linux configs, Wayland gaps,
  and a clipboard-restore race (#502). Worth emulating.
- **Sponsored by Wordcab, Epicenter and Bolt AI.** The brand name, logo and icon are explicitly
  **not** open source even though the code is MIT.

### FluidVoice — the fast riser with a closed core
`altic-dev/FluidVoice`, 11,438 stars, GPL-3.0 since 2026-02-23 (Apache-2.0 before). Swift, macOS
15+. Trendshift-featured.

- **Fluid Intelligence** is a separately maintained, private local AI runtime for smart
  formatting, context-aware capitalization and post-processing. Roughly 3.5 GB model download.
  The maintainers say they keep it private "so we can sustainably offer the core dictation
  experience for free." Strategically important: an open app with a closed differentiator.
- Model table is the widest in the field, with explicit download sizes and per-model language
  lists (Parakeet v3 = 25 languages incl. German; Cohere Transcribe = 14; Whisper = 99).
- Requires macOS 15 (Sequoia), Apple Silicon for all models, Intel only via Whisper since 1.5.1.
- Source files confirm `CustomDictionaryView.swift`, `PronunciationDictionaryStore.swift`,
  `AutomaticDictionaryTrainingSession.swift`, `DictionaryTransferService.swift`,
  `DictionaryAPIController.swift` and a `LocalAPIRouter` — so there is a local HTTP API too.
- **Detailed anonymous analytics are enabled by default** (daily feature/model usage, onboarding
  progress, model download outcomes), opt-out in Settings. Unusual for this category.

### VoiceInk — the one that sells builds
`Beingpax/VoiceInk`, 6,388 stars. Created 2024-10-20, pushed today.

- **Pricing (verified on tryvoiceink.com, 50% promo live):** Solo **$25** (1 Mac, was $49),
  Personal **$39** (2 Macs, was $49), Extended **$49** (3 Macs, was $69). All "lifetime of
  updates", 14-day money-back guarantee. Free trial available.
- **The LICENSE file is verbatim GPLv3** (verified by reading it) even though the GitHub API
  reports the licence as unrecognized/`NOASSERTION`.
- **Not accepting pull requests.** "You're welcome to fork and modify VoiceInk for your own use."
  Buying a licence gets you automatic updates, priority support and funds development.
- `CloudProviderRegistry.allProviders` = Groq, ElevenLabs, Deepgram, Mistral, Gemini, Soniox,
  Speechmatics, AssemblyAI, xAI, Cartesia. The `CloudProvider` protocol carries
  `customVocabulary: [String]` into every call, exposes `makeStreamingProvider(modelContext:)`
  and an `isStreamingOnly` flag for providers with no batch endpoint.
- Local provider directories: `AppleSpeech`, `FluidAudio` (Parakeet/Nemotron), `TranscribeCpp`
  (GGUF), `Whisper` (whisper.cpp via `LibWhisper.swift`, with `WhisperPrompt.swift` for boosting).
- Model registry confirms `ggml-large-v3`, `ggml-large-v3-turbo`, `ggml-large-v3-turbo-q5_0`,
  `ggml-large-v2`, Parakeet V2/V3/Unified, Nemotron Latin/Multilingual, Cohere Transcribe,
  SenseVoice Small, Apple Speech (macOS 26). Parakeet Unified is described as having "native
  realtime transcription support".
- Uses **Sparkle**, `KeyboardShortcuts`, `LaunchAtLogin`, `MediaRemoteAdapter` (pauses media while
  recording), `SelectedTextKit`, `Zip`, `swift-atomics`.

### Blurt — AssemblyAI's strategic entry, and the best code-switching story
`AssemblyAI/blurt`, 5 stars, MIT, Swift 6. **Created 2026-06-30**, released v0.1.53 today. Low
stars purely because it is ten weeks old and unpromoted.

- **Cloud-only, no local models.** One synchronous `POST` to
  `dictation.assemblyai.com/v1/transcribe/live` does STT **and** server-side LLM cleanup in the
  same round trip, typically ~1 second. No upload-then-poll job queue, no daemons.
- **"Multilingual — works in 18 languages, detected automatically, and you can code-switch
  mid-sentence."** The only explicit code-switching claim in the field.
- Claims **30% fewer hallucinations than Whisper** on AssemblyAI's published benchmarks.
- **Key terms** from Settings are sent as the `keyterms-prompt` list to bias spelling
  (`KeytermsBoost` in `Sources/BlurtEngine/STT/`).
- **Contextual priming** is the differentiator and the privacy trade-off: each request carries
  your recent dictations from this session plus a short run of the text immediately before your
  cursor. Password fields are refused. Nothing else about the screen is sent — not the app, window
  title, field or selection. History is memory-only, capped at 100 dictations and ~4096 chars per
  request, cleared on quit. **Note the cross-app leak they document honestly:** text dictated in
  one app can ride along as context with a later dictation in another.
- **Lone-modifier trigger with a unit-tested state machine.** `DictationKeyGate`/`Router` is pure
  and tested; `DictationKeyTap` is the CGEventTap. Tap vs hold vs combo is decided in pure code.
- Latency engineering is explicitly "bookkeeping": `press()` warms the HTTPS connection and starts
  the focused-field context read without awaiting either; `release()` claims the "transcribing"
  state before the recording is even read back from disk, so the stop cue fires at key-up.
- **`BlurtEngine` is a standalone dependency-free Swift 6 package** with three protocol seams,
  fully stubbed in tests, explicitly offered for embedding in other dictation apps.
- Fun differentiator: real **Yamaha DX7 and Roland Juno-106** start/stop cues.
- 6 MB DMG, signed and notarized, **no telemetry of any kind**, and an updater that never replaces
  itself — it only offers to open the DMG.

### Hex — split into legacy and rewrite
`kitlangton/Hex` (2,895 stars) is now a preservation repo for the Swift app; the live project is
`anomalyco/hex` (183 stars, Rust + GPUI, created 2026-07-17).

- The Swift app used Parakeet TDT v3 via FluidAudio, WhisperKit, and Swift Composable
  Architecture. Still gets releases (v0.8.5, 2026-08-27) and a core Homebrew cask.
- The Rust app adds a **Linux beta** (i3/X11 and wlroots Wayland), a TypeScript SDK on npm
  (`@kitlangton/hex`), and optional OpenCode V2 integration for Voice Action and post-processing.
- **Experimental continuous voice commands** with a separate local command model, context-filtered
  by app and Brave website, and user-authored TypeScript commands. Website-aware modes currently
  **require Brave Browser**, which is a notable limitation.
- Settings and history do **not** migrate from the Swift app. Users must quit the old one so the
  shortcuts do not compete.
- History retains pasted text for 7 days by default, never audio, never full URLs or window
  titles, with entry and byte limits on every retention choice.
- Confusing distribution: **GitHub releases hold the SDK, not the app.** The app ships as a DMG
  from R2 plus a Homebrew tap.

### OpenLess — the streaming-insertion and hotword leader
`Open-Less/openless`, 3,498 stars, AGPL-3.0, Rust + Tauri. Bilingual EN/ZH project, created
2026-04-27. Positions against Typeless, Wispr Flow, Lazy and Superwhisper.

- **Streaming insertion writes character by character** to the cursor as text is polished, with
  automatic one-shot-paste fallback for apps that cannot take synthesized keystrokes. Toggle in
  Settings → Recording.
- **The most sophisticated hotword handling here.** Entries go out as real provider-level hotwords
  (Volcengine `context.hotwords`, StepFun `hotwords`, Whisper-compatible `prompt`, Bailian
  vocabulary ID), the budget is a few hundred characters, and entries are **ranked by hit count**
  with reserved seats for recently hand-added words. iFlytek has no request-level hotword param,
  so it documents configuring them in the vendor console instead.
- **Dictionary learns from corrections.** Opt-in `cursor context` (macOS only) reads a few hundred
  chars around your cursor; when you hand-fix a word OpenLess just typed, a card asks whether to
  remember it. Nothing is added silently.
- Local ASR is **Qwen3-ASR 0.6B/1.7B**, not Whisper. Local Whisper is on the roadmap.
- **Not notarized**, ad-hoc signed; README tells users to run a Terminal command to clear the
  "damaged" warning. Own Homebrew tap.
- The README carries a long "from tool to infrastructure" manifesto about "sedimenting"
  repeated decisions into defaults. Good positioning language if you want a narrative.

### OpenWhispr — the enterprise-shaped one
`OpenWhispr/openwhispr`, 8,052 stars, MIT, Electron 41 + React 19 + better-sqlite3 + whisper.cpp +
sherpa-onnx. Released today.

- GPU-accelerated local Whisper on **Metal, CUDA and Vulkan** (AMD/Intel), plus Parakeet via
  sherpa-onnx and Cohere Transcribe.
- Honest Intel-Mac caveat: live speaker identification and voice fingerprinting need ONNX Runtime,
  which stopped shipping macOS x86_64 binaries in 1.24, so those features are unavailable and
  notes search degrades to keyword matching.
- 317 MB macOS DMG — by far the heaviest, a direct consequence of Electron plus bundled runtimes.
- Ships a **dictation-translation hotkey**: dictate in one language, paste in another.
- Enterprise: org policy enforcement, SSO, SCIM, centrally managed Bedrock or Azure OpenAI so
  keys are never distributed. Neon-sponsored cloud backend.

### TypeWhisper — the paid-tier open-source app
`TypeWhisper/typewhisper-mac`, 1,779 stars, GPL-3.0, Swift 6, created 2026-02-12.

- Has a genuine **Premium tier**: meeting automation with calendar connections, correction
  learning in target apps, and Cloud Folder Sync through iCloud Drive / Dropbox / OneDrive /
  Syncthing. The Premium hub shows entitlement state per feature. Exact prices are **not** in the
  repo.
- **The most disciplined release engineering** in the set: Sparkle with stable / release-candidate
  / daily channels, RC and daily builds published as GitHub prereleases and excluded from
  Homebrew, a release-readiness guide, a release checklist issue template, and a support matrix.
- Localized UI in **English, German, Japanese and Simplified Chinese**; dictionary term packs are
  localized in English and German.
- Plugin SDK (`TypeWhisperPluginSDK`) with an integration marketplace and bulk plugin updates.
- Explicit mention that "live transcript updates can write into active text fields" while "final
  insertion remains authoritative" — the cleanest description of the streaming-plus-final problem
  anyone here gives.

### Muesli — dictation plus meetings, agent-native
`Muesli-HQ/muesli`, 1,206 stars, MIT, Swift, created 2026-03-05.

- Quotes **~0.13 s dictation latency** via Parakeet TDT on the Apple Neural Engine.
- Default model is Parakeet Unified English (~565 MB); multilingual Parakeet v3 is ~450 MB.
- Live meeting transcription has two explicit modes: Nemotron 3.5 / Apple Speech own both live
  captions and the final transcript, whereas Parakeet Realtime EOU gives provisional previews
  while a separately selected model produces the final. Settings always shows which model owns the
  final transcript. Off by default.
- **Silero VAD-driven chunk rotation** splits mic audio at natural pauses instead of fixed
  intervals, so no mid-sentence cuts.
- Optional local cleanup with **S1-mini by Superwhisper**, Muesli's own GGUF cleanup models, or
  on-device Gemma 4 E2B.
- `muesli-cli` is explicitly aimed at Codex and Claude Code, exposing meetings, dictations, raw
  transcripts, notes and local file transcription as stable JSON, plus a `--dictionary` flag.
- iCloud syncs text and metadata only, **never audio**.
- Signing line says "Developer ID + hardened runtime (notarization ready)" — I would not claim
  notarized on that wording alone.

### The small and the dormant
- **WhisperDictation** (`sam-pop`, 8 stars) punches above its weight on two points. Its
  **commit-on-pause live dictation** types each phrase about half a second after you pause and
  **never revises already-typed text**, which makes it safe in terminals and send-on-enter chat
  boxes — the single best answer to the streaming-safety problem in this whole set. And it ships
  **500+ built-in technical terms** (API, JSON, Kubernetes, PostgreSQL, GraphQL) as a Whisper
  prompt, user-editable. whisper.cpp is compiled as a static lib with embedded Metal, so there are
  no dynamic library dependencies. Explicitly **not notarized**. Only Base/Small/Medium models.
- **MiniWhisper** (`andyhtran`, 33 stars) is the cleanest minimal reference: menu bar only,
  Parakeet + whisper.cpp, Option+W toggle, Escape to cancel, text replacements, history, WPM
  stats, own Homebrew tap, `sign-and-notarize` recipes using `asc`. Includes a nice UX touch —
  a hint about macOS hiding menu bar icons, shown the first three launches.
- **OpenSuperWhisper** (`Starmel`, 2,861 stars) has the richest trigger options (single modifier
  incl. Fn, **mouse buttons**, hold-to-record) and drag-and-drop file queues, but its contribution
  TODO list still has **streaming transcription and custom dictionary / keyword boosting
  unchecked**, and its only release is 0.1.0 from 2026-03-03 despite recent pushes.
- **Amical** (`amicalhq`, 1,526 stars) is Electron, still on beta tags, with 189–201 MB macOS
  artifacts. Requires building whisper.cpp from a submodule. Android on Play Store, iOS in beta.
  Linux unsupported for lack of a native helper.
- **Voquill** (`voquill`, 1,008 stars, AGPL-3.0, Tauri) has the most product-shaped screenshots:
  Writing Styles (Polished / Verbatim / Chat), Dictionary with terms and replacement rules,
  Providers page for BYOK, Chats, and a Home page with streaks and WPM. Repo contains desktop,
  mobile, docs site, enterprise services, CLI and shared packages. Last push 2026-08-01.
- **whisper-writer** (`savbell`, 1,100 stars) is **effectively dead** — no push since
  2024-08-24. Python + PyQt5, faster-whisper locally or OpenAI API with a configurable
  `base_url`, `initial_prompt` for boosting, continuous recording mode. Historically interesting
  as one of the first in this category; not a live competitor.
- **Whispering** (Epicenter monorepo, 4,797 stars) is architecturally the odd one out: a single
  SvelteKit SPA that builds for both browser and Tauri via `#platform/*` module conditions. Local
  GGUF transcription, system-global shortcuts, native paste and the floating overlay exist **only**
  in the desktop build. Providers are `epicenter` (hosted gateway), OpenAI, Groq, ElevenLabs,
  Deepgram, Mistral, `local`, and `speaches` (self-hosted). A `TranscriptionCapabilities` type
  exposes `supportsPrompt` and `supportsLanguage`. ADR-0227 killed the hosted browser deploy.
  The old `braden-w/whispering` repo is **archived** and redirects here.

---

## 7. Closed-source commercial competitors

| Product | Open source | Pricing | Platforms | Notes |
|---|---|---|---|---|
| **Voibe** (getvoibe.com) | No | $7.50/mo, $59/yr, **$149 lifetime** | Mac + Windows; on-device needs Apple Silicon M1+ | Whisper on the Neural Engine, "true dictionary injection", Push-to-Talk + Hands-Free + Live Dictation. Private cloud, no BYOK. |
| **Spokenly** (spokenly.app) | No | Free with local models + BYOK; **Pro $9.99/mo**, no lifetime | Mac + iOS, no Windows app | Whisper **Large-v3** and NVIDIA Parakeet locally; BYOK across OpenAI, Deepgram, Groq, Anthropic, Google; or Pro managed cloud through five subprocessors. Custom dictionary via post-processing. |
| **Willow Voice** (willowvoice.com) | No | ~$12–15/mo, ~$144/yr; 2,000 free words/week | Mac, iOS, Windows (Jan 2026) | Cloud-first, Offline Mode is opt-in. Custom vocabulary, context-aware formatting. |
| **Sotto** (sotto.to, by Kitze) | No | not verified | macOS | **Do not confuse with the OSS repos.** "Sotto" is shared by at least six unrelated GitHub projects, the largest of which (`evertjr/Sotto`) has 13 stars. No significant OSS Sotto exists. |

Pricing for Voibe, Spokenly and Willow came from competitor-marketing comparison pages
(getvoibe.com and tryvoiceink.com), not from the vendors' own pricing pages, with the exception of
Willow whose numbers were cross-referenced. **Treat these figures as indicative and re-check
before quoting them anywhere externally.**

---

## 8. Things I could not verify

Listed rather than guessed.

1. **Whispering's licence.** The GitHub API reports the Epicenter monorepo as `NOASSERTION`; I did
   not read the LICENSE file. The 4,797 star count is for the whole monorepo, not Whispering.
2. **large-v3 availability** for OpenWhispr, Whispering, Hex (either version), Amical, Voquill and
   MiniWhisper. All support Whisper in some form; I did not find an explicit large-v3 entry.
3. **Custom vocabulary and streaming for OpenWhispr, Amical and Voquill.** Voquill's README
   describes glossary terms and replacement rules but does not say whether they reach the ASR or
   run as post-processing.
4. **Notarization for FluidVoice, VoiceInk, TypeWhisper, Muesli, OpenSuperWhisper and Amical.**
   All are in the homebrew-cask core tap (or an official tap) with no Gatekeeper caveat, which
   strongly implies signed and notarized builds. I confirmed a notarization step in CI **only for
   Handy**. FluidVoice has no release workflow in its repo at all, so its DMGs are built locally.
   Muesli's own wording is "notarization ready".
5. **TypeWhisper Premium pricing.** The tier exists and is documented; no prices are in the repo
   and I did not find a pricing page.
6. **Bundle sizes** are GitHub release asset sizes, not installed footprints, and they exclude
   model weights. Models add roughly 250 MB to 2.9 GB depending on choice, plus ~3.5 GB for
   FluidVoice's optional Fluid Intelligence model and ~565 MB for Muesli's default Parakeet.
7. **Intra-utterance German/English code-switching.** Only Blurt claims it. Several apps ship
   models that cover German, but none of the others make the mixed-utterance claim, and I found no
   benchmark data either way.
8. **Handy's `custom_words` prompt path per model.** I confirmed the fuzzy fallback in source and
   the comment stating Unicode words "remain available to models that accept them as native decode
   prompts", but did not trace which of the bundled models actually accept them.

---

## 9. Source URLs

Repositories: [Handy](https://github.com/cjpais/Handy) ·
[FluidVoice](https://github.com/altic-dev/FluidVoice) ·
[OpenWhispr](https://github.com/OpenWhispr/openwhispr) ·
[VoiceInk](https://github.com/Beingpax/VoiceInk) ·
[Whispering](https://github.com/EpicenterHQ/epicenter/tree/main/apps/whispering) ·
[OpenLess](https://github.com/Open-Less/openless) ·
[Hex legacy](https://github.com/kitlangton/Hex) ·
[Hex Rust](https://github.com/anomalyco/hex) ·
[OpenSuperWhisper](https://github.com/Starmel/OpenSuperWhisper) ·
[TypeWhisper](https://github.com/TypeWhisper/typewhisper-mac) ·
[Amical](https://github.com/amicalhq/amical) ·
[Muesli](https://github.com/Muesli-HQ/muesli) ·
[whisper-writer](https://github.com/savbell/whisper-writer) ·
[Voquill](https://github.com/voquill/voquill) ·
[Blurt](https://github.com/AssemblyAI/blurt) ·
[MiniWhisper](https://github.com/andyhtran/MiniWhisper) ·
[WhisperDictation](https://github.com/sam-pop/WhisperDictation)

Product sites: [handy.computer](https://handy.computer) ·
[tryvoiceink.com](https://tryvoiceink.com) · [assemblyai.com/blurt](https://www.assemblyai.com/blurt) ·
[hex.kitlangton.dev](https://hex.kitlangton.dev/) · [openless.top](https://openless.top) ·
[amical.ai](https://amical.ai) · [muesli.works](https://muesli.works) ·
[voquill.com](https://voquill.com) · [openwhispr.com](https://openwhispr.com) ·
[docs.openwhispr.com](https://docs.openwhispr.com) ·
[sam-pop.github.io/WhisperDictation](https://sam-pop.github.io/WhisperDictation/)

Closed-source competitors: [spokenly.app/comparison](https://spokenly.app/comparison) ·
[getvoibe.com/resources/voibe-vs-spokenly](https://www.getvoibe.com/resources/voibe-vs-spokenly/) ·
[willowvoice.com/pricing](https://willowvoice.com/pricing) ·
[getvoibe.com/resources/willow-voice-review](https://www.getvoibe.com/resources/willow-voice-review/) ·
[tryvoiceink.com/best-spokenly-alternatives](https://tryvoiceink.com/best-spokenly-alternatives) ·
[tryvoiceink.com/best-willow-voice-alternatives](https://tryvoiceink.com/best-willow-voice-alternatives) ·
[sotto.to](https://sotto.to/)
