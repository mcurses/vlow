"""Persist the most recent raw audio buffer to disk.

Always overwrites a single file so a crashed transcription, hung disconnect,
or accidental discard never loses the audio. The user can re-transcribe by
hand from the saved WAV.
"""

import os
import subprocess
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000

LATEST_PATH = Path.home() / "Library" / "Application Support" / "vlow" / "last_recording.wav"


def _ensure_dir() -> None:
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)


def _write_wav(pcm16: bytes) -> None:
    """Write 16-bit mono 16 kHz PCM atomically (tmp + rename)."""
    _ensure_dir()
    tmp = LATEST_PATH.with_suffix(".wav.tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16)
    os.replace(tmp, LATEST_PATH)


def save_float32(audio: np.ndarray) -> Path | None:
    """Save a float32 numpy buffer (batch Recorder output)."""
    if audio is None or audio.size == 0:
        return None
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    _write_wav(pcm16)
    return LATEST_PATH


def save_int16_bytes(pcm16: bytes) -> Path | None:
    """Save already-int16-encoded PCM (streaming session captures int16 directly)."""
    if not pcm16:
        return None
    _write_wav(pcm16)
    return LATEST_PATH


def reveal_in_finder() -> bool:
    """Highlight last_recording.wav in Finder. Returns False if the file is missing."""
    if not LATEST_PATH.exists():
        return False
    subprocess.run(["open", "-R", str(LATEST_PATH)], check=False)
    return True
