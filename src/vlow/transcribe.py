import os

import numpy as np

VALID_BACKENDS = ("mlx", "assemblyai")


def backend_name() -> str:
    name = (os.environ.get("VLOW_BACKEND") or "mlx").lower()
    if name not in VALID_BACKENDS:
        raise ValueError(
            f"VLOW_BACKEND={name!r} not in {VALID_BACKENDS}"
        )
    return name


def _backend():
    if backend_name() == "assemblyai":
        from . import transcribe_aai as m
    else:
        from . import transcribe_mlx as m
    return m


def warmup() -> None:
    _backend().warmup()


def transcribe(audio: np.ndarray) -> str:
    return _backend().transcribe(audio)
