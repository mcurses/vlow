"""Queue of in-flight batch transcriptions.

Stopping a recording used to block the hotkey until the text came back. Here
a stop only enqueues, so you can keep dictating while earlier recordings are
still being transcribed. Each queued job is one glass blob in the overlay.

Two constraints shape the design:

* **On-device inference is single-threaded.** parakeet_mlx is pinned to a
  one-worker pool and `mlx_whisper.transcribe` would race on Metal state, so
  "mlx" jobs run strictly one at a time. AssemblyAI jobs are plain HTTP and
  run in parallel.
* **Text must land in the order it was spoken — per target app.** A job waits
  for older jobs that paste into the *same* app, but never for one headed
  somewhere else. Dictating into Slack should not be held up because a long
  recording for Notes is still uploading.

Delivery itself is serialized through a single worker: pasting activates
apps and rewrites the clipboard, so two at once would interleave badly.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import recordings
from .transcribe import resolve_backend, transcribe

# Parallel AssemblyAI uploads. Beyond a handful the account's concurrency
# limit, not our thread count, is the bottleneck.
CLOUD_WORKERS = 3


@dataclass
class Job:
    seq: int
    target: object | None  # NSRunningApplication the text belongs to
    target_key: object  # what "same app" means for ordering (pid, or None)
    audio: np.ndarray = field(repr=False)
    audio_path: Path | None = None
    text: str = ""
    error: str = ""
    done: bool = False  # transcription finished (successfully or not)

    @property
    def id(self) -> str:
        """Stable identity for the overlay blob's glassEffectID."""
        return f"job{self.seq}"


class TranscriptionQueue:
    """Owns every batch transcription that has been recorded but not pasted."""

    def __init__(
        self,
        deliver: Callable[[Job], None],
        on_change: Callable[[], None],
        log: Callable[[str], None] = lambda msg: None,
    ) -> None:
        """`deliver` pastes one job's text (called on the delivery thread, in
        order). `on_change` fires whenever the pending set changes, so the
        caller can refresh the overlay and menubar."""
        self._deliver = deliver
        self._on_change = on_change
        self._log = log
        self._lock = threading.Lock()
        self._jobs: list[Job] = []  # pending only; dropped once delivered
        self._seq = 0
        self._local = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vlow-local")
        self._cloud = ThreadPoolExecutor(
            max_workers=CLOUD_WORKERS, thread_name_prefix="vlow-cloud"
        )
        # max_workers=1 → the executor's own FIFO queue is what keeps pastes
        # in submission order.
        self._delivery = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="vlow-paste"
        )

    # ── public API ──────────────────────────────────────────────────────

    def submit(self, audio: np.ndarray, target) -> Job:
        """Enqueue a finished recording. Returns immediately."""
        with self._lock:
            self._seq += 1
            job = Job(
                seq=self._seq,
                target=target,
                target_key=_app_key(target),
                audio=audio,
            )
            self._jobs.append(job)
            depth = len(self._jobs)

        # Persist before any transcription so a crash never loses the audio.
        try:
            job.audio_path = recordings.save_pending(job.seq, audio)
            recordings.save_float32(audio)  # keep last_recording.wav current
        except Exception as e:
            self._log(f"saving queued recording failed: {e}")

        backend = "assemblyai"
        try:
            backend = resolve_backend(audio)
        except Exception as e:  # bad config — let the run surface it
            self._log(f"backend resolution failed: {e}")
        pool = self._cloud if backend == "assemblyai" else self._local
        self._log(
            f"queued {job.id} ({audio.size / 16000:.1f}s → {backend}, depth {depth})"
        )
        pool.submit(self._run, job)
        self._on_change()
        return job

    def pending_ids(self) -> list[str]:
        """Blob ids, oldest first — what the overlay draws."""
        with self._lock:
            return [j.id for j in self._jobs]

    def depth(self) -> int:
        with self._lock:
            return len(self._jobs)

    def is_busy(self) -> bool:
        return self.depth() > 0

    def shutdown(self) -> None:
        for pool in (self._local, self._cloud, self._delivery):
            pool.shutdown(wait=False, cancel_futures=True)

    # ── internals ───────────────────────────────────────────────────────

    def _run(self, job: Job) -> None:
        started = time.monotonic()
        try:
            job.text = transcribe(job.audio)
        except Exception as e:
            job.error = str(e)
            self._log(f"{job.id} failed after {time.monotonic() - started:.1f}s: {e!r}")
        finally:
            # Freeing the buffer here matters: a deep queue of long recordings
            # would otherwise hold every PCM array until the last paste.
            job.audio = np.zeros(0, dtype=np.float32)
            job.done = True
            self._flush()

    def _flush(self) -> None:
        """Hand every unblocked finished job to the delivery thread, oldest
        first. A job is unblocked when no *earlier* job for the same target
        app is still pending."""
        with self._lock:
            ready: list[Job] = []
            blocked_keys: set = set()
            for job in self._jobs:  # seq order
                if not job.done or job.target_key in blocked_keys:
                    # Everything after this, for this app, has to wait.
                    blocked_keys.add(job.target_key)
                    continue
                ready.append(job)
            for job in ready:
                self._jobs.remove(job)
        if not ready:
            return
        for job in ready:
            self._delivery.submit(self._deliver_one, job)
        self._on_change()

    def _deliver_one(self, job: Job) -> None:
        try:
            if job.text.strip():
                self._deliver(job)
        except Exception as e:
            self._log(f"{job.id} delivery failed: {e!r}")
        finally:
            recordings.discard_pending(job.audio_path)


def _app_key(target) -> object:
    """Ordering bucket for a job. Same pid → same queue; no target (paste
    wherever focus is) → one shared bucket, which means strict order."""
    if target is None:
        return None
    try:
        return int(target.processIdentifier())
    except Exception:
        return None
