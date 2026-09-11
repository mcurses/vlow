# vlow vs. the 2026 dictation market

Research date: 2026-09-11. vlow state: v0.1.0 released 2026-09-10, 2 GitHub stars, no
LICENSE file. Three raw research reports sit next to this file (`oss-research.md`,
`commercial-research.md`, `gap-research.md`); every claim below is sourced there.

## Bottom line

vlow's feature *list* is not unique. Local Whisper + cloud BYOK + custom vocabulary +
menubar hotkey + floating pill exists in at least ten shipping apps, several with
thousands of stars. What is unique is three pieces of *behaviour*, none of which any
competitor was found to ship:

1. **Duration-based automatic local/cloud routing** (`backend = auto`). Every "hybrid"
   competitor (HyperWhisper, Wave, Spokenly, VoiceInk) makes the user pick a mode by hand.
   AssemblyAI's own dictation-API guidance describes exactly vlow's split.
2. **A gesture bound to a pipeline**: hold → live streaming with progressive paste,
   double-tap → batch. Everyone else treats push-to-talk vs toggle as pure ergonomics.
   Streaming is the loudest unmet request on Hacker News across four separate threads.
3. **MLX as the on-device runtime.** No popular dictation app uses it. Roughly 2× faster
   than whisper.cpp on the same model, though ~5× slower than Parakeet on the Neural Engine.

The headline claim vlow *does* make, German/English code-switching, is the one that is
**not** well supported by evidence on the local path. Whisper's maintainers say Whisper is
not built for code-switching; the one independent benchmark ranks Whisper last on DE/EN.
The cloud path (AssemblyAI) is near the top of the same benchmark. That inversion is the
main thing to fix before pitching.

## The field

Popularity signals verified on 2026-09-11 (GitHub API, Apple iTunes API, first-party pages).

### Open source, same product category

| App | Stars | Stack | Local engines | Cloud BYOK | Streaming | Vocabulary | Signed | Size |
|---|---:|---|---|---|---|---|---|---|
| Handy | 31.4k | Rust/Tauri | whisper.cpp, Parakeet | LLM only, no cloud STT | model-gated | prompt + fuzzy | notarized | 18 MB |
| FluidVoice | 11.4k | Swift | Nemotron, Parakeet, Whisper, Apple | OpenAI, Groq | live preview | yes + auto-learn | likely | 47 MB |
| OpenWhispr | 8.1k | Electron | whisper.cpp, Parakeet | many | not for dictation | unconfirmed | ? | 317 MB |
| VoiceInk | 6.4k | Swift, sells builds $25–49 | whisper.cpp, Parakeet, Nemotron, Apple | 10 providers incl. AssemblyAI | per provider | dictionary + smart replace | likely | 47 MB |
| OpenLess | 3.5k | Rust/Tauri | Qwen3-ASR | 12+ | char-by-char | provider hotwords + learning | **ad-hoc** | ? |
| Hex (Swift) | 2.9k | Swift | Parakeet, WhisperKit | no | no | no | ? | 14 MB |
| TypeWhisper | 1.8k | Swift | WhisperKit, Parakeet, Apple, Voxtral… | Groq, OpenAI, Soniox… | WhisperKit preview | yes + term packs (DE) | likely | 13 MB |
| Muesli | 1.2k | Swift | Parakeet (ANE), Nemotron, WhisperKit | OpenAI realtime | meetings only | fuzzy dictionary | "notarization ready" | 98 MB |
| Blurt (AssemblyAI) | 5 | Swift | none | AssemblyAI only | no | keyterms | notarized | 6 MB |
| **vlow** | 2 | Python + SwiftUI | MLX whisper large-v3 | AssemblyAI | **hold gesture, cloud** | all backends incl. streaming | **ad-hoc** | ~600 MB |

### Commercial

| App | Signal | Price | Local STT | BYOK | Streaming | Code-switching stance |
|---|---|---|---|---|---|---|
| Wispr Flow | $280M raise at $2B, 15k iOS ratings | $15/mo | none | no | no | FAQ: pick one language, "rapid switching not supported" |
| Superwhisper | 100k+ weekly actives | free local Whisper since 2.18.2; Pro $8.49/mo, $250 lifetime | whisper large-v3, Parakeet | Pro | Deepgram cloud only | docs admit auto-detect often outputs English |
| MacWhisper | Gumroad 4.5★ / 2,572 reviews | €64 lifetime | WhisperKit, Parakeet | 14+ | no | docs: cannot do two languages in one file |
| Spokenly | closed, weekly releases | free + BYOK, Pro $9.99 | whisper large-v3, Parakeet | yes incl. **AssemblyAI realtime + keyterms since 2026-07-27** | yes | no claim; App Store sandboxed |
| Monologue | 291 iOS ratings | $15/mo | partial (cleanup is cloud) | no | ? | **best documented**: select up to 3 languages, mid-sentence OK |
| Apple Dictation (macOS 26) | built in | free | ~40 locales on-device | n/a | inline preview | manual switching only; no vocabulary; no push-to-talk |

## Where vlow genuinely stands out

- **Auto routing by duration.** Confirmed absent everywhere. Vendor-endorsed architecture.
- **Hold = stream, double-tap = batch, with progressive paste.** Nobody binds pipeline to
  gesture. Nearest things: OpenLess's character streaming (cloud, Chinese-first), Spokenly's
  AssemblyAI realtime (manual mode, sandboxed), WhisperDictation's commit-on-pause (local, tiny).
- **Known words reach every backend, including the streaming session.** Handy and VoiceInk
  apply vocabulary per model; Superwhisper is the only commercial app that biases the model
  rather than post-replacing. Not a marketing line on its own, but it makes the routing
  invisible: the same names come out right whichever backend ran.
- **MLX runtime.** Engineering differentiation, weak as a user-facing story.
- **Plain `config.toml` written live by the Settings window.** The most substantive
  independent review of the category (A Fading Thought) argues incumbents are stripping
  customisation; a diffable config file is a direct answer.
- **Raw recording always on disk before any network call.** Nobody else documents this.
- **Not App Store sandboxed.** Same as most direct-download competitors, but it is
  Spokenly's single structural weakness and got TongueType rejected from the store.

## Where vlow does not stand out, or is behind

- **Local Whisper large-v3 is table stakes.** Handy, VoiceInk, FluidVoice, TypeWhisper,
  Superwhisper, MacWhisper and Spokenly all ship it. Superwhisper made all local Whisper
  models free on 2026-08-26.
- **Only one model, 3 GB, Apple Silicon only.** Every peer offers a model picker with
  small/turbo/Parakeet options. Parakeet on the ANE is ~5× faster than mlx-whisper and beat
  Deepgram and Mistral on the DE/EN pair in the ServiceNow benchmark.
- **Streaming requires a paid cloud key.** Handy (Nemotron 3.5), FluidVoice, TypeWhisper
  and Muesli now stream locally.
- **600 MB bundle, Python, ad-hoc signed, Accessibility re-prompt after every update.**
  Handy is 18 MB and notarized in CI; Blurt is 6 MB. Ad-hoc signing puts vlow in the same
  "run xattr in Terminal" bucket as OpenLess and WhisperDictation.
- **The glass pill is table stakes.** Muesli, Willow, Handy, FluidVoice, Blurt all have a
  pill; WrapScribe offers nine anchor points and an off switch. Ours has drag and persist;
  it needs an off switch to be competitive, not more polish.
- **No history, no AI cleanup, no modes.** Deliberate, and defensible, but Handy's reviews
  list "no AI cleanup" as a rough edge, so some users will bounce.
- **AssemblyAI integration is no longer unique.** Spokenly shipped realtime + keyterms six
  weeks ago; VoiceInk lists AssemblyAI among ten providers; AssemblyAI ships Blurt itself.
- **Model versions are stale.** vlow requests `universal-3-pro` (batch) and `u3-rt-pro`
  (streaming). AssemblyAI launched Universal-3.5 Pro Realtime on 2026-09-08 with native
  mid-sentence code-switching in 18 languages, 285 ms median time-to-final, keyterms
  included. On 3.5 Pro, `language_detection=True` alone enables code-switching.
- **No LICENSE file.** Without one the repo is source-available, not open source, and
  Homebrew core will not take the cask. Handy's "most forkable" positioning depends on MIT.

## The code-switching problem

The README says vlow "handles per-token German/English code-switching". Evidence:

- Whisper emits one language token per 30-second window (OpenAI maintainer, whisper
  discussion #2009: "doesn't support code-switching inputs very well"). With no language
  set, mixed audio was **translated into English**; `--language de` preserved all
  languages as spoken.
- ServiceNow-AI seven-system benchmark: Whisper large-v3-**turbo** last on DE/EN
  (WER 0.16–0.61); AssemblyAI Universal-3 Pro and ElevenLabs Scribe v2 top tier;
  Parakeet TDT v3 strong specifically on DE/EN. No published number exists for
  non-turbo large-v3, which is what vlow ships.
- vlow's MLX path passes no `language`, so it relies on auto-detect, the mode the
  discussion above found harmful for mixed speech.
- Demand is real and unanswered: VoiceInk issue #611 (German/English user, open, zero
  replies), #617 (Turkish/English, closed as duplicate). Wispr Flow, MacWhisper and Apple
  document the limitation; Superwhisper overclaims it.

So the claim is currently strongest on the backend the README calls optional and weakest
on the default. Nobody has published a real DE/EN mixed-utterance number for a dictation
app; publishing one would itself be a differentiator.

## Recommended positioning

> Two engines, one vocabulary, one really good recording flow. Hold to stream, tap to
> batch, and it picks local or cloud for you.

Not "the powerful one" (VoiceInk, Superwhisper, TypeWhisper own that) and not "the tiny
forkable one" (Handy, Blurt own that). vlow is the one whose *routing* is automatic.
The Denglisch angle is the sharpest launch hook in the field, but only after it is
measured and after the local path is fixed or honestly scoped.

Launch reality check: two Show HN breakouts in three years (Whispering 591 pts,
Ghost Pepper 467 pts), everything else under 40 points, and a thread quote of "a support
group for people who have each independently built the same macOS speech-to-text app".
A generic "local Whisper dictation for Mac" post will not land.

## Concrete follow-ups, in priority order

1. **Add a LICENSE** (MIT to match Handy's forkability story, or GPLv3 like VoiceInk).
2. **Measure DE/EN code-switching** on the actual pipeline: a small corpus of mixed
   utterances, WER per backend, with and without `language="de"` on MLX. Fix the README
   claim to whatever the number says.
3. **Move AssemblyAI to Universal-3.5 Pro** for batch and realtime; verify keyterms and
   `language_detection` parameters against the 3.5 docs.
4. **Consider routing on detected language mix, not only duration.** No app routes on
   content at all. That would make "auto" mode a real second differentiator.
5. **Evaluate Parakeet TDT v3 as a second local engine** (via MLX or CoreML). Faster,
   better on DE/EN in the one benchmark, 450 MB. Keeps large-v3 for the 99-language case.
6. **Developer ID + notarization.** The workflow already supports it; the current
   Accessibility re-prompt on every update is the worst first-week experience in the set.
7. **Overlay off switch and anchor setting.** Cheap, and reviewers count it.
8. **Publish latency numbers, not model size.** The market is judging on time-to-text.
