import numpy as np
import mlx_whisper

from .config import known_words

MODEL = "mlx-community/whisper-large-v3-mlx"
MIN_SAMPLES = 1600


def _initial_prompt() -> str | None:
    """Whisper biases token probabilities toward names listed in initial_prompt.
    A short natural-language sentence works better than a bare list."""
    words = known_words()
    if not words:
        return None
    return "Words and names that may appear: " + ", ".join(words) + "."


def warmup() -> None:
    silence = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(silence, path_or_hf_repo=MODEL, verbose=False)


def transcribe(audio: np.ndarray) -> str:
    if audio.size < MIN_SAMPLES:
        return ""
    # Anti-repetition-loop settings. Whisper's autoregressive decoder is prone to
    # falling into "Das ist die Situation. Das ist die Situation. …" style loops,
    # especially on German/mixed-language audio with thinking pauses. The defaults
    # let one bad 30s window poison every following window via the prompt feedback.
    kwargs = {
        "path_or_hf_repo": MODEL,
        "verbose": False,
        "condition_on_previous_text": False,
        "compression_ratio_threshold": 2.0,
        "hallucination_silence_threshold": 2.0,
    }
    prompt = _initial_prompt()
    if prompt:
        kwargs["initial_prompt"] = prompt
    result = mlx_whisper.transcribe(audio, **kwargs)
    return result["text"].strip()
