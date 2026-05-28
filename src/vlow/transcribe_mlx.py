import numpy as np
import mlx_whisper

MODEL = "mlx-community/whisper-large-v3-mlx"
MIN_SAMPLES = 1600


def warmup() -> None:
    silence = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(silence, path_or_hf_repo=MODEL, verbose=False)


def transcribe(audio: np.ndarray) -> str:
    if audio.size < MIN_SAMPLES:
        return ""
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=MODEL,
        verbose=False,
    )
    return result["text"].strip()
