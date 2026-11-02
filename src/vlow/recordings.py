"""Keep the most recent raw audio buffers on disk, with their transcripts.

Every recording, batch or streaming, is written before any transcription so a
crashed transcription, hung disconnect or accidental discard never loses the
audio. The newest KEEP recordings stay in RECORDINGS_DIR as
``<timestamp>.wav``; once a recording has been transcribed its text sits next
to it as ``<timestamp>.txt``. Older pairs are deleted as new ones arrive.
"""

import os
import subprocess
import threading
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
KEEP = 3

_DIR = Path.home() / "Library" / "Application Support" / "vlow"
RECORDINGS_DIR = _DIR / "recordings"
# Before 0.3.2 only the newest recording was kept, always under this name.
_LEGACY_PATH = _DIR / "last_recording.wav"
# One file per queued-but-not-yet-delivered recording. The rolling set above
# only holds the newest KEEP, so without these a crash with more jobs in
# flight would lose the older ones.
PENDING_DIR = _DIR / "pending"

_lock = threading.Lock()
_last_new: datetime | None = None


def _stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]


def _new_path() -> Path:
    """A name that sorts after every earlier one: two saves in the same
    millisecond (an emergency save right after a stop) must not share it."""
    global _last_new
    now = datetime.now()
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    if _last_new is not None and now <= _last_new:
        now = _last_new + timedelta(milliseconds=1)
    _last_new = now
    return RECORDINGS_DIR / f"{_stamp(now)}.wav"


def _write_wav(path: Path, pcm16: bytes) -> None:
    """Write 16-bit mono 16 kHz PCM atomically (tmp + rename)."""
    tmp = path.with_suffix(".wav.tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16)
    os.replace(tmp, path)


def _migrate_legacy() -> None:
    """Move a last_recording.wav from an older vlow into the rolling set."""
    if not _LEGACY_PATH.exists():
        return
    when = datetime.fromtimestamp(_LEGACY_PATH.stat().st_mtime)
    os.replace(_LEGACY_PATH, RECORDINGS_DIR / f"{_stamp(when)}.wav")


def recordings() -> list[Path]:
    """Saved recordings, oldest first."""
    if not RECORDINGS_DIR.exists():
        return []
    return sorted(RECORDINGS_DIR.glob("*.wav"))


def latest() -> Path | None:
    found = recordings()
    return found[-1] if found else None


def _prune() -> None:
    for old in recordings()[:-KEEP]:
        old.unlink(missing_ok=True)
        old.with_suffix(".txt").unlink(missing_ok=True)


def _save(pcm16: bytes) -> Path:
    with _lock:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        _migrate_legacy()
        path = _new_path()
        _write_wav(path, pcm16)
        _prune()
        return path


def save_float32(audio: np.ndarray) -> Path | None:
    """Save a float32 numpy buffer (batch Recorder output)."""
    if audio is None or audio.size == 0:
        return None
    return _save((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def save_int16_bytes(pcm16: bytes) -> Path | None:
    """Save already-int16-encoded PCM (streaming session captures int16 directly)."""
    if not pcm16:
        return None
    return _save(pcm16)


def save_transcript(recording: Path | None, text: str) -> Path | None:
    """Write `text` next to its recording as <name>.txt. Skipped when there is
    no text, or when the recording has already been pruned by newer ones."""
    if recording is None or not text.strip():
        return None
    with _lock:
        if not recording.exists():
            return None
        path = recording.with_suffix(".txt")
        tmp = path.with_suffix(".txt.tmp")
        tmp.write_text(text.strip() + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return path


def reveal_in_finder() -> bool:
    """Highlight the newest recording in Finder. Returns False if there is none."""
    path = latest()
    if path is None:
        return False
    subprocess.run(["open", "-R", str(path)], check=False)
    return True


def save_pending(seq: int, audio: np.ndarray) -> Path | None:
    """Keep a queued recording on disk until its text has been delivered."""
    if audio is None or audio.size == 0:
        return None
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    path = PENDING_DIR / f"{seq:06d}.wav"
    _write_wav(path, (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return path


def discard_pending(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)


def sweep_pending() -> int:
    """Drop leftovers from a previous run (delivered text, killed process).
    Returns how many files were removed."""
    if not PENDING_DIR.exists():
        return 0
    n = 0
    for f in PENDING_DIR.glob("*.wav"):
        f.unlink(missing_ok=True)
        n += 1
    return n
