import importlib
import os
import time

import numpy as np

VALID_BACKENDS = ("mlx", "assemblyai", "auto")
SAMPLE_RATE = 16000
DEFAULT_AUTO_THRESHOLD_SEC = 60.0


def backend_name() -> str:
    name = (os.environ.get("VLOW_BACKEND") or "mlx").lower()
    if name not in VALID_BACKENDS:
        raise ValueError(f"VLOW_BACKEND={name!r} not in {VALID_BACKENDS}")
    return name


def auto_threshold_sec() -> float:
    raw = os.environ.get("VLOW_AUTO_THRESHOLD_SEC")
    if not raw:
        return DEFAULT_AUTO_THRESHOLD_SEC
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(
            f"VLOW_AUTO_THRESHOLD_SEC={raw!r} is not a number"
        ) from e


def _backend_for_audio(audio: np.ndarray) -> str:
    """Pick the concrete backend for a specific buffer; honors auto mode."""
    name = backend_name()
    if name != "auto":
        return name
    duration = audio.size / SAMPLE_RATE
    return "assemblyai" if duration > auto_threshold_sec() else "mlx"


def _module(name: str):
    if name == "assemblyai":
        from . import transcribe_aai as m

        return m
    # "mlx" is whichever on-device model is selected (config: local_model).
    from .local_models import selected

    return importlib.import_module(f".{selected().module}", __package__)


def warmup() -> None:
    name = backend_name()
    if name == "auto":
        # Both paths must be ready: mlx loads weights, aai verifies the key.
        _module("mlx").warmup()
        _module("assemblyai").warmup()
    else:
        _module(name).warmup()


def transcribe(audio: np.ndarray) -> str:
    chosen = _backend_for_audio(audio)
    duration = audio.size / SAMPLE_RATE
    if chosen == "mlx":
        from .local_models import selected_key

        label = f"mlx/{selected_key()}"
    else:
        label = chosen
    if backend_name() == "auto":
        print(f"[vlow] auto: {duration:.1f}s → {label}", flush=True)
    # Log how long it actually took, not just which backend ran. Without this
    # a slow dictation is unattributable: the mlx path can re-decode a window
    # up to 6 times on low confidence (~6x swing), while the assemblyai path
    # is a network upload whose latency has nothing to do with the model.
    # xN is speed relative to realtime — higher is faster.
    start = time.monotonic()
    try:
        return _module(chosen).transcribe(audio)
    finally:
        elapsed = time.monotonic() - start
        # Suppress the ratio on a near-instant return: that means the backend
        # raised, and a five-digit speedup in the log is just noise.
        speed = f" (x{duration / elapsed:.1f} realtime)" if elapsed >= 0.1 else ""
        print(
            f"[vlow] {label}: {elapsed:.1f}s for {duration:.1f}s audio{speed}",
            flush=True,
        )
