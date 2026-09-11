import numpy as np
import mlx.core as mx
import mlx_whisper

from .config import known_words
from .local_models import MODELS, ModelNotDownloaded, is_downloaded

WHISPER = MODELS["whisper-large-v3"]

MIN_SAMPLES = 1600


def _initial_prompt() -> str | None:
    """Whisper biases token probabilities toward names listed in initial_prompt.
    A short natural-language sentence works better than a bare list."""
    words = known_words()
    if not words:
        return None
    return "Words and names that may appear: " + ", ".join(words) + "."


def _release_buffers() -> None:
    """Hand MLX's reusable GPU buffers back to the system.

    MLX keeps freed Metal buffers in a cache to make the next allocation cheap.
    Nothing ever shrinks that cache, so in a daemon it only ratchets upward:
    ~0.9 GB after warmup, ~2.2 GB after a single 45s dictation, and it stays
    there for as long as the agent runs. That is real wired GPU memory —
    it shows up under IOAccelerator in `footprint`, not in RSS, which is why
    Activity Monitor reports gigabytes for a process `ps` calls 37 MB.

    Clearing it does not touch the loaded model (2.88 GB of *active* memory),
    so the hotkey stays instant; only the between-dictation slack is returned.
    Cheap enough to run after every transcription, and vlow is idle >99% of
    the time, so the cache buys nothing while it sits there."""
    mx.clear_cache()


def warmup() -> None:
    if not is_downloaded(WHISPER):
        raise ModelNotDownloaded(WHISPER)
    silence = np.zeros(16000, dtype=np.float32)
    try:
        mlx_whisper.transcribe(silence, path_or_hf_repo=WHISPER.repo, verbose=False)
    finally:
        _release_buffers()


def transcribe(audio: np.ndarray) -> str:
    if audio.size < MIN_SAMPLES:
        return ""
    if not is_downloaded(WHISPER):
        raise ModelNotDownloaded(WHISPER)
    # Anti-repetition-loop settings. Whisper's autoregressive decoder is prone to
    # falling into "Das ist die Situation. Das ist die Situation. …" style loops,
    # especially on German/mixed-language audio with thinking pauses. The defaults
    # let one bad 30s window poison every following window via the prompt feedback.
    kwargs = {
        "path_or_hf_repo": WHISPER.repo,
        "verbose": False,
        "condition_on_previous_text": False,
        "compression_ratio_threshold": 2.0,
        "hallucination_silence_threshold": 2.0,
    }
    prompt = _initial_prompt()
    if prompt:
        kwargs["initial_prompt"] = prompt
    try:
        result = mlx_whisper.transcribe(audio, **kwargs)
    finally:
        _release_buffers()
    return result["text"].strip()
