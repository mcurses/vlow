"""On-device push-to-talk streaming via parakeet-mlx.

Same shape as stream_aai.StreamingSession — start(), stop(), the same
callbacks — so app.py can pick either at runtime. Only Parakeet can do this:
it is a Conformer/TDT transducer, decoded frame-synchronously against a
rotating KV cache, so audio can be fed in as it arrives. Whisper attends over
whole 30 s windows and would have to re-transcribe a growing buffer instead.

**When text is committed.** The library only moves tokens from `draft` to
`finalized` once their audio has aged out of the encoder cache, which with a
256-frame context is far too late to paste live. So this uses LocalAgreement:
a prefix is committed once `AGREE_CHUNKS` successive decodes agree on it, cut
back to the last whole word. That matters because a progressive paste is
irreversible — it has already gone into somebody else's document. Measured on
real dictation, agreeing over two 0.5 s chunks still committed text the model
later revised ("zu gesagt" → "zugesagt", "114" → "14"); three chunks did not,
while still committing ~97% of the transcript live. The remainder is flushed
by stop(), which is also where releasing the key naturally lands.

The whole session runs as one task on transcribe_parakeet's single worker
thread: MLX streams are thread-bound, and transcribe_stream() switches the
encoder to local attention for its duration, so a batch decode running
alongside would both race and read the wrong attention mode.
"""

import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
# 0.5 s per decode. Shorter chunks commit sooner but cost a decode each; this
# lands around 300 ms of work per chunk, comfortably realtime.
CHUNK_SAMPLES = 8000
# Mic blocksize is deliberately *not* CHUNK_SAMPLES. The level meter is driven
# from the audio callback and the overlay advances one bar per push, so tying
# the callback to the decode size made the waveform crawl at 2 fps. Let
# PortAudio pick its natural (small) block, exactly as the batch Recorder
# does, and accumulate up to CHUNK_SAMPLES here before handing the decoder a
# chunk. 256 frames is 16 ms — comfortably above the ~29 pushes/s the overlay
# wants, without the ~1000 callbacks/s PortAudio's own default produced here.
MIC_BLOCKSIZE = 256
# How many successive decodes must agree before a prefix is pasted. Three is
# the smallest value that never retracted on real dictation — see module docs.
AGREE_CHUNKS = 3
# Encoder KV cache window (kept frames, dropped frames).
CONTEXT_SIZE = (256, 256)
# A pinch of silence pushed before any real audio, so the one-off ~1.8 s cost
# of building the cache is paid while the user is still drawing breath rather
# than swallowing their first word.
PRIMER_SAMPLES = 1600
# How much of the already-pasted tail to match against a revised draft when
# lining the two up.
_ANCHOR_CHARS = 40


def _common_prefix(a: str, b: str) -> str:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return a[:n]


class StreamingSession:
    def __init__(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
        device: Optional[int] = None,
    ) -> None:
        self._on_partial = on_partial or (lambda _: None)
        self._on_final = on_final or (lambda _: None)
        self._on_level = on_level
        self._device = device  # None → system default at start()
        self._queue: "queue.Queue[Optional[np.ndarray]]" = queue.Queue()
        self._pending: list[np.ndarray] = []  # mic blocks not yet a full chunk
        self._pending_len = 0
        self._raw_chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._committed = ""  # everything handed to on_final so far
        self._drafts: list[str] = []
        self._final_text = ""
        self._stream: Optional[sd.InputStream] = None
        self._future = None

    # ── lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        from . import transcribe_parakeet as backend

        # Load before opening the mic so a missing model surfaces as an error
        # here rather than as silence after the user has started talking.
        backend.submit_to_worker(backend.load_model).result()

        from .audio import refresh_devices

        refresh_devices()
        self._future = backend.submit_to_worker(self._run)
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=MIC_BLOCKSIZE,
            callback=self._audio_cb,
            device=self._device,
        )
        self._stream.start()

    def _audio_cb(self, indata: np.ndarray, frames, time_info, status) -> None:
        mono = indata.reshape(-1).astype(np.float32).copy()
        self._raw_chunks.append(
            (np.clip(mono, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        )
        # Every block feeds the meter, so the waveform moves at the mic's
        # natural rate rather than once per decode.
        if self._on_level is not None:
            try:
                self._on_level(float(np.sqrt(np.mean(np.square(mono)))))
            except Exception:
                pass  # never let a UI hiccup break capture
        self._pending.append(mono)
        self._pending_len += mono.size
        if self._pending_len >= CHUNK_SAMPLES:
            self._queue.put(np.concatenate(self._pending))
            self._pending = []
            self._pending_len = 0

    # ── inference (worker thread) ───────────────────────────────────────

    def _run(self) -> None:
        import mlx.core as mx

        from . import transcribe_parakeet as backend

        model = backend.load_model()
        try:
            with model.transcribe_stream(context_size=CONTEXT_SIZE) as st:
                st.add_audio(mx.array(np.zeros(PRIMER_SAMPLES, dtype=np.float32)))
                while True:
                    chunk = self._queue.get()
                    if chunk is None:
                        break
                    st.add_audio(mx.array(chunk))
                    self._advance(st.result.text.strip())
                self._finish(st.result.text.strip())
        except Exception as e:
            print(f"[stream_mlx] session error: {e!r}", flush=True)

    def _tail_after(self, candidate: str) -> Optional[str]:
        """The part of `candidate` that follows everything already pasted.

        Usually `candidate` still starts with what we pasted and this is a
        plain slice. But the decoder revises earlier words as context grows
        ("Spracherkennung" → "Spracherkung"), which shifts every offset after
        them — slicing by length then lands mid-word, which is how "Der Text"
        once became "Der Text ext". So when the prefix no longer matches, line
        the two up on the tail of what we pasted instead. Returns None when
        they cannot be lined up at all, in which case we commit nothing this
        round and wait for the drafts to settle: pasting is irreversible, so
        emitting nothing is always safer than emitting a duplicate.
        """
        pasted = self._committed
        if not pasted:
            return candidate
        if candidate.startswith(pasted):
            return candidate[len(pasted):]
        anchor = pasted[-_ANCHOR_CHARS:]
        i = candidate.rfind(anchor)
        return None if i < 0 else candidate[i + len(anchor):]

    def _advance(self, draft: str) -> None:
        """Commit whatever the last AGREE_CHUNKS decodes agree on."""
        self._drafts.append(draft)
        if len(self._drafts) < AGREE_CHUNKS:
            return
        stable = self._drafts[-1]
        for older in self._drafts[-AGREE_CHUNKS:-1]:
            stable = _common_prefix(stable, older)
        with self._lock:
            tail = self._tail_after(stable)
            cut = tail.rfind(" ") if tail else -1  # whole words only
            if cut <= 0:
                self._emit_partial(draft)
                return
            text = tail[:cut]
            # Grow by exactly what we hand out, so _committed stays a faithful
            # record of what is in the user's document.
            self._committed += text
        if text.strip():
            self._on_final(text.strip())
        self._emit_partial(draft)

    def _emit_partial(self, draft: str) -> None:
        tail = self._tail_after(draft)
        if tail and tail.strip():
            self._on_partial(tail.strip())

    def _finish(self, draft: str) -> None:
        """Release stopped the mic: everything still uncommitted is final."""
        with self._lock:
            tail = self._tail_after(draft) or ""
            self._committed += tail
            final = self._committed
        self._final_text = final
        if tail.strip():
            self._on_final(tail.strip())

    # ── teardown ────────────────────────────────────────────────────────

    def snapshot_pcm16(self) -> bytes:
        """Raw PCM16 captured so far, without stopping (SIGTERM emergency save)."""
        return b"".join(list(self._raw_chunks))

    def stop(self) -> str:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

        # Persist before waiting on the decoder, so even a wedged session
        # can't lose the audio.
        if self._raw_chunks:
            try:
                from .recordings import save_int16_bytes

                save_int16_bytes(b"".join(self._raw_chunks))
            except Exception as e:
                print(f"[stream_mlx] save raw failed: {e}", flush=True)

        if self._pending:  # trailing audio shorter than a full chunk
            self._queue.put(np.concatenate(self._pending))
            self._pending = []
            self._pending_len = 0
        self._queue.put(None)  # ends the worker loop, which flushes the tail
        if self._future is not None:
            try:
                self._future.result(timeout=30)
            except Exception as e:
                print(f"[stream_mlx] worker did not finish: {e!r}", flush=True)
            finally:
                self._future = None
        with self._lock:
            # What was actually pasted — the closing draft can be worse than
            # text committed earlier, since tokens degrade as they age out.
            return (self._final_text or self._committed).strip()
