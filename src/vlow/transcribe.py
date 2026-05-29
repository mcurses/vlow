import os

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
    else:
        from . import transcribe_mlx as m
    return m


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
    if backend_name() == "auto":
        duration = audio.size / SAMPLE_RATE
        print(f"[vlow] auto: {duration:.1f}s → {chosen}", flush=True)
    return _module(chosen).transcribe(audio)
