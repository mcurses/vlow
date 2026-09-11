# Research Report: vlow positioning, market gaps

Research date: 2026-09-11. Web research only, no code changes.

Bottom line up front: the single most important finding is that **Whisper is the worst
available model for German/English code-switching**, both architecturally and empirically.
That conflicts with vlow's headline differentiator on its local path. Meanwhile AssemblyAI
shipped native realtime code-switching three days ago, which is vlow's strongest asset, but
a competitor already ships that integration.

---

## 1. Code-switching and mixed-language dictation

### Whisper cannot do this by design

The constraint is architectural: Whisper emits one language token per 30-second window, so it
commits to a single language across the whole segment. An OpenAI maintainer states it directly
in [openai/whisper discussion #2009](https://github.com/openai/whisper/discussions/2009):

> "It's intended for monolingual audio inputs...Whisper doesn't support code-switching inputs
> very well."

And from the same thread, the mechanism:

> "Whisper commits to one language token per 30-second window and so will either transcribe
> English as Marathi or vice versa"

That thread also contains a directly relevant test. A user fed in audio containing German,
English and Spanish segments. With no language parameter set, Whisper **translated everything
into English** instead of transcribing it. Setting `--language de` explicitly preserved all
three languages as spoken. Larger models (medium/large) did better at multi-language detection
regardless of task settings. **The explicit-language-code workaround is worth knowing and worth
testing in vlow.**

### Empirical confirmation, and it is brutal

The [ServiceNow-AI code-switching benchmark](https://huggingface.co/blog/ServiceNow-AI/code-switching)
tested seven systems across four language pairs including German-English:

| System | Standing on code-switched audio |
|---|---|
| ElevenLabs Scribe V2 | Top tier |
| AssemblyAI Universal-3 Pro | Top tier (0.02-0.13 behind) |
| Google Gemini 3 Flash | Close third |
| Deepgram Nova-3 Multilang | Middle, variable by pair |
| Mistral Voxtral Small 24B-2507 | Middle, variable by pair |
| Nvidia Parakeet TDT 0.6b V3 | Middle, but strong on German-English |
| OpenAI Whisper Large V3 Turbo | Last, WER 0.16-0.61 |

Whisper ranked last, and again defaulted to translation rather than transcription when not given
explicit language parameters. The benchmark's summary judgement: Whisper is "unsuitable for
production bilingual scenarios without explicit language configuration."

Two findings inside that benchmark matter for vlow specifically:

1. **Parakeet TDT v3 beat both Deepgram and Mistral on the German-English pair specifically**,
   closing gaps it did not close on other pairs.
2. ElevenLabs Scribe V2, Gemini 3 Flash and AssemblyAI Universal-3 Pro showed the **smallest
   deltas versus their own monolingual baselines**, meaning genuine robustness to bilingual
   input rather than luck.

**Caveat, flagged as important:** the benchmark used large-v3-**turbo**, not the large-v3 that
vlow ships. Turbo is a distilled model with documented multilingual regressions, so vlow's path
is likely better than 0.16-0.61. But the one-language-token-per-window limit applies to both
models equally. I could not find any published large-v3 (non-turbo) code-switching number.
**This specific gap is unverified and nobody appears to have measured it.**

A second study, [Benchmarking Commercial ASR Systems on Code-Switching Speech: Arabic, Persian,
and German](https://arxiv.org/abs/2605.19069) (2026-05-25, Abdoli et al.), benchmarked five
commercial providers on four pairs including German-English, 300 samples per pair. ElevenLabs
Scribe v2 achieved the lowest WER at 13.2% overall and led on BERTScore at 0.936. The paper makes
a useful methodological point: **WER inflates the magnitude of quality gaps by roughly 3x** by
penalising semantically correct transliteration choices. Per-system German-only numbers were not
extractable from the PDF, so **treat that paper's German detail as unverified.**

### Competitor support, app by app

- **Wispr Flow** documents the limitation explicitly. [Their help centre](https://docs.wisprflow.ai/articles/3191899797-use-flow-with-multiple-languages)
  states: *"Rapid language switching within a single sentence is not supported."* Detection is
  session-level, not word-by-word; Flow transcribes the entire segment in one language. They do
  note that English paired with Spanish, French or German works better than English with Chinese
  or Japanese. 100+ languages with an auto-detect option.

- **MacWhisper** is the clearest admission of failure. [Their own support doc](https://macwhisper.helpscoutdocs.com/article/23-multiple-languages-in-a-file)
  says it cannot transcribe files containing multiple languages and advises transcribing the file
  twice, once per language, then combining the results **manually**. The developers say they are
  "looking into ways to improve this in the future."

- **Apple Dictation** still cannot switch languages mid-sentence in 2026, per
  [this analysis](https://dictaflow.io/blog/apple-dictation-multilingual-language-switching-2026.html):
  *"You're either dictating in English or you're dictating in French. Not both."* The workflow is
  stop, change keyboard language, restart dictation, switch back. The article uses "a German
  technical term" as its example of what Apple Dictation gets wrong. It also concludes that **none**
  of the alternatives it reviews achieve true real-time code-switching; they work around it with
  custom vocabulary or faster manual switching.

- **Superwhisper** markets 100+ languages with automatic detection and third-party reviews claim
  mid-sentence English/Spanish switching works. But its own
  [language detection doc](https://superwhisper.com/docs/common-issues/language-detection) concedes
  that in Automatic mode, non-English dictation is often incorrectly transcribed as English. One
  user reported a German-language mode consistently transcribing in English, eventually solved
  with a prompt workaround. **Marketing claims mid-sentence switching; documentation does not back it.**

- **Handy** is local-only with no cloud backends. Per [the repo](https://github.com/cjpais/Handy),
  it uses `transcribe-cpp` (whisper.cpp, GGML/GGUF) for Whisper-family models and `transcribe-rs`
  for CPU-optimised Parakeet. Models: Whisper Small (487 MB), Medium (492 MB), Turbo (1.6 GB),
  Large (1.1 GB), plus Parakeet V3 with automatic language detection. Silero VAD. Tauri (Rust +
  React). MIT licence. macOS/Windows/Linux. **No MLX, no cloud, no streaming, no custom-vocabulary
  feature.** Language-related issues, all closed:

  | Issue | Title | Status |
  |---|---|---|
  | #1275 | Filler word removal incorrectly removes German word "um" (false positive) | Closed 2026-04-13 |
  | #1206 | Canary 1b v2 — text auto translated to English when autodetect on | Closed 2026-07-03 |
  | #1265 | Non-English model shown in English list | Closed 2026-07-03 |
  | #1687 | Language "Auto Detect" missing for many models | Closed 2026-07-15 |
  | #1981 | Norwegian missing from language picker for Nemotron Streaming 3.5 | Closed |

  Note #1206 is the same translate-instead-of-transcribe failure mode as Whisper, and #1981
  reveals Handy has added a **Nemotron Streaming 3.5** model. No open mixed-language or
  code-switching issue.

- **VoiceInk** has the most direct demand signal in the entire research.
  [Issue #611](https://github.com/Beingpax/VoiceInk/issues/611), **open**, filed 2026-03-26 by
  NikolaiGoMedicus, is a German-English user asking for a language toggle hotkey:

  > "I use VoiceInk in both German and English throughout the day — sometimes even within the
  > same app."

  The example given is a German email then English Slack, both in the browser. The requester
  explicitly distinguishes this from issue #499 (keyboard-layout auto-switch, which fails because
  you often type in one language and dictate in another) and #228 (Power Mode profile hotkeys,
  too heavyweight). The ask is a two-language toggle plus a menu-bar indicator of the active
  language. **No comments, no assignee, no labels, no maintainer response.**

  [Issue #617](https://github.com/Beingpax/VoiceInk/issues/617) is a Turkish developer:

  > "None of the current local models are not able to transcribe Turkish with English words."

  They use VoiceInk for development workflows that heavily blend their native language with
  English technical terminology, and they praise Deepgram Nova 3 for handling it, attributing it
  to "architecture and multilingual training data variety." **Closed as duplicate with no
  maintainer discussion or resolution.**

  [Issue #561](https://github.com/Beingpax/VoiceInk/issues/561) covers the iOS keyboard extension
  registering as English-only regardless of the selected model, even with multilingual Parakeet V3.

  VoiceInk's stack: whisper.cpp for Whisper, FluidAudio for Parakeet. **Not MLX.**

### The cloud option that actually works

[AssemblyAI Universal-3.5 Pro Realtime](https://www.assemblyai.com/blog/real-time-transcription-code-switches-multilingual-speakers)
launched **2026-09-08**, three days before this research:

| Property | Value |
|---|---|
| Model ID | `universal-3-5-pro` |
| Code-switching | Native, mid-sentence, no language-detection gateway |
| Languages | 18 incl. German, English, Spanish, French, Italian, Portuguese, Arabic, Danish, Dutch, Finnish, Hebrew, Hindi, Japanese, Chinese, Norwegian, Swedish, Turkish, Vietnamese |
| Median time-to-final | 285 ms |
| p95 / p99 | 374 ms / 443 ms |
| Price | $0.45/hour ($0.0075/min), no premium for code-switched audio |
| Keyterms | Included; general prompting +$0.05/hr |

Claimed gains: 22% relative WER reduction on code-switched audio, plus a further 4% with prompts.
On AssemblyAI's own five-pair code-switching benchmark, Universal-3.5 Pro averages 7.69%
normalized WER against ElevenLabs Scribe v2 at 8.77%, Deepgram Nova-3 Multilingual at 12.22%
and OpenAI GPT-4o Transcribe at 44.58%. (Vendor-published, so weight accordingly — though the
independent ServiceNow benchmark puts AssemblyAI top-tier too.)

**Important for vlow's implementation:** this is Universal-**3.5** Pro, newer than the Universal-3
in vlow's description. Per the
[async code-switching doc](https://www.assemblyai.com/docs/pre-recorded-audio/code-switching),
enabling code-switching differs by model generation:

- **Universal-3.5 Pro:** just set `language_detection: True`. Handles 18 languages natively.
- **Universal-2:** needs `speech_models: ["universal-2"]`, `language_detection: True`, **and**
  `language_detection_options: {code_switching: True}`. Lower quality. Optionally
  `language_codes` to pin exactly 2 languages (one must be English), and a
  `code_switching_confidence_threshold` defaulting to 0.3.

**Check which model and which parameters vlow's backend currently requests.** Getting this wrong
silently costs you the differentiator.

### Other models worth knowing

- **ElevenLabs Scribe v2** leads or ties for the lead on code-switching in both independent
  benchmarks. The arXiv paper notes it "notably outperforms its own L2 baseline, pointing to
  genuine robustness to bilingual input."
- **Mistral Voxtral** claims ~3x faster than Scribe v2 at roughly one-fifth the cost, and
  [Voxtral Realtime](https://arxiv.org/pdf/2602.11298) is competitive with Scribe v2 Realtime on
  FLEURS at 480 ms delay and surpasses both Scribe v2 and Whisper at 960 ms. But it sits mid-tier
  on code-switching specifically. **Cost-effective, not accuracy-leading, for mixed speech.**
- **Deepgram Nova-3 Multilingual** is mid-tier on the independent benchmark (12.22% per
  AssemblyAI's numbers), yet VoiceInk issue #617's author praises it as the one thing that worked
  for Turkish-English. Suggests real-world code-switching performance may not track benchmark
  ranking neatly.

---

## 2. MLX versus whisper.cpp, and Parakeet for German

### MLX is about 2x faster

[Bill Mill's benchmark](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html),
updated 2026-01-09, on large-v3-turbo:

| Implementation | Time |
|---|---|
| mlx_whisper (`mlx-community/whisper-large-v3-turbo`) | 13.135 s (±0.280) |
| whisper.cpp (`ggml-large-v3-turbo.bin`) | 26.704 s (±0.625) |

**2.03x**, up from 1.78x in his earlier run with older model versions. He also notes turbo models
seem somewhat slower than distil models. Hardware was not specified and **no WER was measured, so
the accuracy side of MLX vs whisper.cpp is unverified.**

### But MLX is not the fastest option on a Mac

[mac-whisper-speedtest](https://github.com/anvanvan/mac-whisper-speedtest) compares nine
implementations. On an M4 MacBook Pro with 24 GB, large-class models:

| Implementation | Time | Model |
|---|---|---|
| FluidAudio CoreML | 0.19 s | Parakeet TDT 0.6b v2 |
| Parakeet MLX | 0.50 s | Parakeet TDT 0.6b v2 |
| mlx-whisper | 1.02 s | whisper-large-v3-turbo |
| insanely-fast-whisper | 1.13 s | whisper-large-v3-turbo |
| whisper.cpp (CoreML) | 1.23 s | large-v3-turbo-q5_0 |
| lightning-whisper-mlx | 1.82 s | large |
| WhisperKit | 2.22 s | large-v3 |
| whisper-mps | 5.37 s | large |
| faster-whisper | 6.96 s | large-v3-turbo |

Parakeet on the Neural Engine via CoreML is roughly **5x faster than mlx-whisper**. vlow's 2x win
over whisper.cpp is real, but it sits inside a much larger gap vlow is not contesting. Also note
WhisperKit running true large-v3 (not turbo) takes 2.22 s, which hints at the non-turbo penalty.

### No popular dictation app uses MLX

| App | Runtime |
|---|---|
| VoiceInk | whisper.cpp + FluidAudio (Parakeet via CoreML/ANE) |
| Handy | transcribe-cpp (whisper.cpp) + transcribe-rs (Parakeet) |
| Spokenly | Not stated; release notes never mention MLX |
| Superwhisper | Not published; "consistent runtime internally" |
| Yap | Apple SpeechAnalyzer (macOS 26 native) |
| FnScribe | Quantized Whisper, moving to Moonshine |
| Ghost Pepper | Local Whisper ~466 MB / Parakeet v3 ~1.4 GB |

FluidAudio alone reportedly powers **over 20 production apps** including VoiceInk. There is an
open request for first-class MLX Whisper support in an unrelated project
([NousResearch/hermes-agent #3491](https://github.com/NousResearch/hermes-agent/issues/3491)) and
a long-standing [whisper.cpp issue #1598](https://github.com/ggml-org/whisper.cpp/issues/1598)
asking it to use MLX, so appetite exists.

**vlow would be unusually placed in shipping MLX.** Genuinely differentiated at the engineering
level. But users judge latency, not framework, and the fastest local path on a Mac today is
Parakeet on the ANE.

### Parakeet v3 versus Whisper large-v3 for German

- **English leaderboard:** Parakeet TDT 0.6B v3 averages ~6.3% WER across the eight Open ASR
  Leaderboard benchmarks against ~7.4% for Whisper large-v3
  ([Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)).
  That leaderboard is English-dominated.
- **Specialised German:** the [PARLO German dementia corpus](https://arxiv.org/pdf/2603.03471)
  found Whisper consistently achieved the lowest WER (9-18% depending on task), "substantially
  outperforming the other models," with Parakeet second.
- **Language coverage:** Parakeet v3 covers 25 languages, Whisper large-v3 covers 99.
- **German-English code-switching:** Parakeet beat Deepgram and Mistral on this pair in the
  ServiceNow benchmark, while Whisper Large V3 Turbo came last overall.
- **Reported weaknesses:** [Voibe](https://www.getvoibe.com/resources/voiceink-review/) notes
  Parakeet mis-detects language when switching mid-dictation, recommending users stick to Whisper
  with the language set manually. Handy reviewers flag Parakeet's missing Japanese coverage.

**Reasonable read:** Whisper large-v3 is the safer German choice for monolingual German; Parakeet
is much faster and competitive; and Parakeet is arguably the better *local* option for DE/EN
mixed speech. Several of the supporting sources are competitor-owned SEO blogs (Voibe, Spokenly,
LoroNote, ParlaParla), so weight them accordingly — the arXiv and leaderboard numbers are the
solid ones.

---

## 3. Community sentiment, 2026

Reddit is blocked to this crawler (`reddit.com` returns a 400 for the user agent), so this rests
on Hacker News threads and one substantive independent review. Those are the higher-signal
sources anyway.

The defining quote comes from the [Ghost Pepper thread](https://news.ycombinator.com/item?id=47666024)
(467 points, 200 comments):

> "This thread is a support group for people who have each independently built the same macOS
> speech-to-text app."

A curated alternatives list in that thread names over a dozen near-identical projects: Handy, Hex,
Wordbird, localvoxtral, FluidVoice, Foxsay and more. Another commenter was blunter:

> "I'd straight up drop the comparison to big AI labs. This isn't rebellious or subversive, it's
> downstream of a ton of already-funded work."

### Recurring complaints

**Subscription fatigue — the oldest and loudest.** The original
[superwhisper Show HN](https://news.ycombinator.com/item?id=37204722) (43 points, 48 comments,
2023-08-21) was dominated by it: *"I won't pay monthly for this"* and *"death by 1000 $65/year
apps."* Developer Neil Chudleigh defended the pricing, then added a $165 lifetime tier after
repeated pushback — and later admitted lifetime sales were *"Exactly zero."* In the
[Whispering thread](https://news.ycombinator.com/item?id=44942731) a commenter argued that truly
offline software should never require a subscription, preferring one-time purchases.

**No streaming — the most consistent unmet want.**
- Ghost Pepper: multiple users requested live transcription display during speech rather than
  post-recording processing.
- Whispering: criticised for being unable to handle real-time text display during dictation.
- [Handy's review](https://spokenly.app/blog/handy-review) lists *"No real-time streaming: text
  appears 2 to 5 seconds after you stop speaking"* as rough edge #2 of 7.
- The [Apple Silicon speed thread](https://news.ycombinator.com/item?id=46824361) had a user ask
  for phrase-level streaming; the author explained beam search blocks word-by-word streaming and
  suggested **releasing and re-pressing the hotkey every 5-10 words** as a manual workaround.
  That is a user hacking around the exact gap vlow's hold-to-stream design closes.

**Local-first claims that are not.** Whispering's Show HN claimed "All your data is stored
locally" while supporting OpenAI, Groq and ElevenLabs as providers. **An HN moderator edited the
submission text** to clarify that audio goes to either local or cloud providers depending on user
choice. Worth care in vlow's own copy given the optional AssemblyAI backend — the BYOK model
helps, but the wording has to be precise.

**Bloat and lost customisation.** The most substantive independent review,
[A Fading Thought](https://afadingthought.substack.com/p/best-ai-dictation-tools-for-mac), argues
accuracy, speed and privacy are now commoditised:

> "we're close to hitting a plateau here, AI transcription is getting so good it's almost trivial."

It says the real differentiators are now **workflow philosophy, customisation depth and developer
responsiveness**, and frames the market as "Mystery Box" apps (simple, opaque) versus "Transparent
& Empowering" apps (customisable, open). Per-app criticism:

| App | Criticism |
|---|---|
| Superwhisper | Cluttered settings navigation, removed context-capture features, focus-breaking notifications that cannot be disabled, increasingly hides system prompts. "Abandoning customization in pursuit of mainstream simplicity." Expensive upfront lifetime purchase. |
| VoiceInk | Workflow "fussy" — mode-switching requires starting a recording first, capped at 10 keyboard shortcuts, history reprocessing cumbersome. Essentially free (API costs only). |
| Spokenly | Sandboxed on the Mac App Store, which blocks the Accessibility API needed for advanced context awareness. Essentially free (API costs only). |

**Hotkey ergonomics cut both ways.** Ghost Pepper users found hold-to-talk burdensome, with one
complaining about needing to press and release a talk button while still needing the keyboard for
corrections — friction versus historical Dragon software. Handy's reviewers flag auto-paste landing
in the wrong application if you switch windows during processing, 1-2 seconds of extra activation
delay on Bluetooth microphones, and first words occasionally getting clipped. **The clipping and
wrong-window issues are concrete bugs vlow can simply not have.**

**Overlay UI — less a complaint than a solved-many-ways problem.**
[OpenDictation](https://github.com/kdcokenny/OpenDictation) deliberately keeps visual feedback in
the notch "instead of using floating windows that block your work."
[WrapScribe](https://wrapscribe.com/) offers nine anchor points for its floating pill, a notch
accent, or nothing at all, plus a minimal mode showing just a red dot and timer in the menu bar.
**A liquid-glass pill is table stakes, not a differentiator, and it needs an off switch and a
position setting.**

**LLM cleanup backfires.** Ghost Pepper users reported the cleanup prompt misbehaving: *"If your
transcription is first person...it really wants to 'answer' you, completely ignoring its
instructions."* The Apple Silicon thread author reported small LLMs hallucinating and repeating
few-shot examples, requiring fallback detection, and that better cleanup (N=20 examples) pushed
latency to 1.5-3 s. Handy's review lists "no AI cleanup" as a rough edge, so users want it — but
it is a known source of breakage.

**Multilingual gaps keep surfacing.** The [Yap thread](https://news.ycombinator.com/item?id=49073834)
recorded that users mixing languages reported issues and that **existing alternatives handle
code-switching better** (alternatives unnamed, so unverified which).
[FnScribe](https://news.ycombinator.com/item?id=49475159) was explicitly English-only in alpha and
took direct criticism that Whisper is *"pretty outdated vs parakeet."*

---

## 4. Auto-routing and streaming/batch mode pairing

### Duration-based local/cloud routing: I found nobody doing it

The two closest candidates both turn out to be manual:

- **HyperWhisper** markets a hybrid approach, but
  [its own docs](https://www.hyperwhisper.com/docs/transcription-modes) confirm routing is
  **manual only**. A "mode" stores one transcription engine, one language, post-processing and
  formatting. Each mode commits to exactly one of: On Device, HyperWhisper Cloud, or Your Provider
  (BYOK). Users switch with Ctrl+Shift+K on macOS. The documentation contains **no automatic
  routing logic based on duration, network conditions or content type.**
- **Wave** ([Product Hunt](https://www.producthunt.com/products/wave-16), 307 upvotes, launched
  2026-06-07, #2 day rank, free and open source, macOS only) is positioned as "local or cloud,
  your choice." The maker: *"Works locally for privacy. Or via APIs if you want."* Explicitly a
  user choice, with no routing. No multilingual or code-switching claims at all.
- **QuickDictate** (Windows) offers cloud-or-offline mode switching, again manual.

Interestingly, AssemblyAI's own
[dictation API guide](https://www.assemblyai.com/blog/what-is-a-dictation-api) endorses vlow's
exact architecture:

> "Short single-utterance clips where a user is waiting suit a synchronous dictation API; full
> recordings suit a pre-recorded transcription API; continuous live audio suits a streaming
> WebSocket API."

and

> "Most dictated notes run well under a minute, and longer recordings should route to pre-recorded
> transcription, which has no practical duration ceiling."

**The architecture is vendor-endorsed and unimplemented in shipping apps.** That is a real gap.
The commonly cited threshold is around 60 seconds, which is a useful default for vlow's "auto"
mode.

### Streaming-for-hold, batch-for-double-tap: also nobody

Push-to-talk versus toggle is a well-understood distinction and widely discussed — push-to-talk
for short frequent dictation, toggle for longer passages where you do not want to hold a key. The
case for hold-to-talk is made well in
[DictaFlow's post](https://dictaflow.io/blog/hold-to-talk-dictation.html): *"Hold-to-talk turns
dictation into an intentional action; if you are not holding the key, you can think in silence."*
Also argued by [Speechcap](https://www.speechcap.com/blog/the-case-for-push-to-talk) and
[Ryan Shrott](https://medium.com/@ryanshrott/hold-to-talk-is-the-missing-feature-in-modern-dictation-and-why-always-on-fails-b49ed70d5802).

But **I found no app that binds a different transcription pipeline to each gesture.** Gesture
choice everywhere is about comfort, not about batch-versus-streaming. Given how loudly HN asks for
streaming across at least four separate threads, this is a genuinely novel interaction design and
probably vlow's most defensible UX idea.

### AssemblyAI streaming with live paste: one competitor already ships it

[Spokenly's macOS release notes](https://spokenly.app/releases/macos) are the single most
important competitive document in this research:

| Version | Date | Change |
|---|---|---|
| 2.18.9 | 2026-03-30 | Improved AssemblyAI transcription support |
| 2.18.11 | 2026-03-31 | Real-time transcription with Apple Speech Analyzer |
| 2.20.0 | 2026-05-09 | Deepgram Flux for low-latency streaming |
| 2.22.0 | 2026-06-04 | On-device Nemotron 3.5 for multilingual dictation |
| 2.23.0 | 2026-06-18 | NVIDIA Parakeet Unified, fully on-device |
| 2.25.2 | 2026-07-15 | Tunable Parakeet Unified latency (speed vs energy) |
| 2.26.0 | 2026-07-24 | **AssemblyAI Universal 3.5 Pro dictation**; live transcription with ElevenLabs Scribe |
| 2.27.0 | 2026-07-27 | **Improved AssemblyAI support with realtime dictation and keyterms** |
| 2.27.2 | 2026-07-29 | GPT Transcribe with streaming |
| 2.27.5 | 2026-07-31 | ElevenLabs keyterms on every transcription, not just live |
| 2.28.0 | 2026-08-16 | Cohere Transcribe Q4, 14 languages |
| 2.28.5 | 2026-08-27 | Gemini 3.5 Transcribe |
| 2.29.0 | 2026-09-05 | Language, keyterms and text cleanup in MAI-Transcribe 2 |

**Spokenly shipped AssemblyAI realtime dictation with keyterms on 2026-07-27**, six weeks before
this research. It has no MLX and no automatic local/cloud routing. Its structural weakness is Mac
App Store sandboxing blocking the Accessibility API. **This is vlow's most direct competitor and
it ships roughly weekly.**

Also relevant: Handy has added Nemotron Streaming 3.5 (per closed issue #1981), so streaming is
arriving in the open-source tier too. [Sonora](https://github.com/topics/dictation-app) is
described as a real-time STT desktop app with cloud or local models, global hotkey, live streaming
and paste at cursor — **worth a direct look, as it may be the closest existing thing to vlow's
streaming design.** I did not verify Sonora in depth; **flagged as unverified.**

### Known-words across backends

OpenWhispr, DictateDash, Amical and VoxType all advertise custom dictionaries alongside
local/cloud switching. Spokenly applies keyterms per-provider (AssemblyAI, ElevenLabs,
MAI-Transcribe 2). AssemblyAI includes keyterms prompting free on Universal-3.5 Pro Realtime.
DictaFlow's whole multilingual pitch is *custom vocabulary to recognise foreign words regardless
of the active language model* — a workaround for code-switching, at $7/month.

**Applying one known-words list uniformly across every backend is a nice engineering property but
not a marketable differentiator.** However, DictaFlow's angle suggests a known-words list seeded
with English technical terms is a legitimate *partial* answer to Denglisch on the local Whisper
path, which vlow already has the machinery for.

---

## 5. Launch crowding

Show HN outcomes for macOS dictation apps, 2023-2026:

| Launch | Points | Comments | Date |
|---|---|---|---|
| Whispering | 591 | 152 | 2025-08-18 |
| Ghost Pepper | 467 | 200 | ~2026-04 |
| Handy | 247 | n/a | 2025 (*unverified — from search snippet, not fetched*) |
| superwhisper | 43 | 48 | 2023-08-21 |
| OpenWhisper | 37 | 15 | ~2026-03 |
| FnScribe | 36 | 25 | 2026-09-01 |
| TongueType | 5 | 1 | 2026 |
| "local STT shockingly fast on Apple Silicon" | 2 | 3 | ~2026-02 |
| Voibe | 1 | 1 | ~2025-10 |

Other Show HN entries found but not individually fetched: Ito AI, Yap, Dictator (Hammerspoon),
"Open-source macOS dictation replacement, 5Mb", plus repeat Handy submissions
(#45399106, #46628397) — repeat posting is itself a sign of how hard traction is.

Product Hunt has been considerably kinder:

| Product | Upvotes | Comments | Date | Rank |
|---|---|---|---|---|
| Wave | 307 | n/a | 2026-06-07 | #2 of day |
| Lispr | 290 | 52 | 2026-07-09 | #5 of day |
| Handy | — | — | — | 4.9/5 average rating |

**Read: the Hacker News distribution is bimodal and brutal.** Two breakouts in three years, both
open source, both with a sharp story. Everything else lands under 40 points. Handy's 247 came with
a human hook — the author broke a finger and could not type. FnScribe, launched ten days before
this research, drew explicit saturation criticism: commenters noted "over two dozen entries"
tracked in a relevant subreddit and criticised low differentiation and insufficient research into
existing solutions.

Bundle size is a live competitive axis. Yap made a virtue of being **4 MB with no model download**,
using Apple's macOS 26 SpeechAnalyzer, and benchmarked Apple's model as slightly ahead of Whisper
Small on accuracy and about 3x faster. FnScribe's author moved to Moonshine specifically to cut
startup overhead from larger models. Handy's largest model is 1.6 GB. **vlow's ~600 MB sits in the
middle; lead with latency numbers rather than model size.**

**A generic "local Whisper dictation for Mac" launch will not land in 2026.** The launch needs the
sharp, verifiable, specific claim — which is the German/English code-switching story, if the
numbers hold up.

---

## Gaps nobody is filling

1. **Duration-based automatic local/cloud routing.** Confirmed absent from HyperWhisper (manual
   modes), Wave (user choice) and every app checked — yet explicitly endorsed by AssemblyAI's own
   architectural guidance. The strongest structural differentiator vlow has.

2. **Streaming bound to hold, batch bound to toggle.** No app pairs a gesture to a *pipeline*.
   Streaming is simultaneously the loudest unmet request on Hacker News, appearing in the Ghost
   Pepper, Whispering, Apple Silicon and Handy-review threads independently. One HN user was
   manually re-pressing the hotkey every 5-10 words to fake it.

3. **Honest, benchmarked German-English code-switching in a dictation app.** Every incumbent either
   documents the failure (MacWhisper, Apple, Wispr Flow) or overclaims it (Superwhisper). VoiceInk
   #611 and #617 are live, unanswered demand. **Nobody has published a real DE/EN mixed-utterance
   number for a dictation app.** Publishing one would be novel on its own.

4. **Denglisch as an explicit, named use case.** German technical and developer speech is
   structurally code-switched. Only generic German dictation vendors mention Denglisch at all, and
   no Mac dictation app targets it. Germany is a large, privacy-conscious, willing-to-pay market
   that every incumbent addresses only as "one of 100+ languages."

5. **MLX as a shipping runtime.** Genuinely unoccupied — 2x whisper.cpp on large-v3-turbo, though
   ~5x slower than Parakeet on the Neural Engine. Differentiated engineering, weak marketing story
   on its own.

6. **Power-user transparency.** A Fading Thought's central argument is that incumbents are sanding
   off customisation in pursuit of the mainstream. A readable, diffable, version-controllable
   `config.toml` is a direct answer to a complaint someone wrote a long essay about.

7. **Not being sandboxed.** Spokenly's single biggest structural limitation is Mac App Store
   sandboxing blocking the Accessibility API. vlow's ad-hoc signed DMG plus Homebrew tap sidesteps
   that entirely. TongueType was outright **rejected from the Mac App Store under Guideline 2.4.5**
   over Accessibility API usage, so this is a category-wide constraint, not a one-off.

---

## Two positioning risks to weigh

### The code-switching claim points at the wrong backend

Explicit German/English handling is vlow's best story, but **Whisper is the worst model for it and
Whisper's own maintainers say so in writing.** AssemblyAI Universal-3.5 Pro is near the top of the
independent benchmark. So the local path is weakest exactly where vlow claims strength, and the
cloud path is strongest.

Three implications:

1. **Consider routing detected mixed-language utterances to cloud regardless of duration.** That
   would make "auto" mode route on *detected language mixing*, not only duration — which as far as
   this research shows would be genuinely new. No app routes on content at all.
2. **Evaluate Parakeet v3 on the local DE/EN path.** It beat Deepgram and Mistral on the German-English
   pair specifically, it is ~5x faster than mlx-whisper via CoreML/ANE, and FluidAudio makes it
   accessible. The tradeoff is 25 languages versus 99 and reported mid-dictation detection wobble.
3. **Measure vlow's own large-v3 DE/EN WER before publishing any claim.** Nobody has that number,
   including me. If it is bad, the honest positioning is "code-switching works via the cloud
   backend, and here is the measured local number" — which is still stronger than every competitor,
   all of whom either fail silently or overclaim.

Also: force the explicit language code on the local path. The Whisper discussion shows
`--language de` preserved German, English and Spanish as spoken, while auto-detect translated
everything to English. Auto-detect on Whisper is actively harmful for mixed speech.

### Spokenly is ahead on the cloud differentiator

It has shipped AssemblyAI realtime plus keyterms since 2026-07-27 and iterates roughly weekly
across a dozen backends. vlow's remaining edges over it: progressive paste, the hold/double-tap
gesture split, duration-based routing, no App Store sandbox, open source, and MLX. That is still a
real set — but "we integrate AssemblyAI streaming" is not by itself a differentiator any more.

---

## Verification status

**Solidly sourced:** Whisper's architectural code-switching limitation and the maintainer quote;
the ServiceNow seven-system benchmark ranking; AssemblyAI Universal-3.5 Pro Realtime specs and
launch date; MacWhisper's and Wispr Flow's documented inability to code-switch mid-sentence;
VoiceInk issues #611/#617/#561; Handy's stack, models and closed language issues; Spokenly's
release-note timeline; the two MLX benchmarks; all Show HN point counts except Handy's; HyperWhisper's
manual-only routing.

**Unverified or weakly sourced — flagged:**
- Whisper large-v3 **non-turbo** code-switching performance. No published number exists. The
  benchmark that ranked Whisper last used large-v3-turbo.
- Per-system German-only numbers in arXiv 2605.19069. PDF body was not extractable.
- Handy's 247 HN points. From a search snippet; the thread was not fetched directly.
- Bill Mill's benchmark hardware and any accuracy comparison between MLX and whisper.cpp.
- Which "alternatives handle code-switching better" per the Yap thread. Unnamed.
- Sonora's feature set. Surfaced once, not investigated.
- Superwhisper's inference runtime. Not published anywhere found.
- All Voibe, Spokenly-blog, LoroNote, ParlaParla, DictaFlow, Whisperer and getwspr claims are
  competitor-owned SEO content and should be treated as marketing, not evidence.
- Reddit sentiment. `reddit.com` is blocked to this crawler; section 3 rests on Hacker News plus
  one independent Substack review.
