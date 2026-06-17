import os
import tempfile
import wave

import numpy as np

from .config import known_words

MODELS = ["universal-3-pro", "universal-2"]
MIN_SAMPLES = 1600
SAMPLE_RATE = 16000


def _build_config():
    """Build a fresh AssemblyAI TranscriptionConfig per call so changes to
    known_words in config.toml take effect without restarting vlow."""
    import assemblyai as aai

    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError(
            "Set ASSEMBLYAI_API_KEY in env to use the assemblyai backend."
        )
    aai.settings.api_key = key

    extras: dict = {"speech_models": MODELS}
    lang = os.environ.get("VLOW_AAI_LANGUAGE")
    if lang:
        extras["language_code"] = lang
    else:
        extras["language_detection"] = True

    words = known_words()
    if words:
        # keyterms_prompt biases the universal-3 models; word_boost covers the
        # universal-2 fallback. Both can be set safely.
        extras["keyterms_prompt"] = words
        extras["word_boost"] = words
        extras["boost_param"] = "high"

    return aai.TranscriptionConfig(**extras)


def warmup() -> None:
    # No network — just import the SDK and verify the API key is set so a
    # missing key fails fast at app startup instead of mid-dictation.
    _build_config()


def transcribe(audio: np.ndarray) -> str:
    if audio.size < MIN_SAMPLES:
        return ""
    import assemblyai as aai

    config = _build_config()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            w.writeframes(pcm16)
        transcript = aai.Transcriber(config=config).transcribe(path)
        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(f"AssemblyAI: {transcript.error}")
        return (transcript.text or "").strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
