import os
import tempfile
import wave

import numpy as np

MODELS = ["universal-3-pro", "universal-2"]
MIN_SAMPLES = 1600
SAMPLE_RATE = 16000

_config = None


def _get_config():
    """Lazily build the AssemblyAI TranscriptionConfig and verify the key."""
    global _config
    if _config is not None:
        return _config
    import assemblyai as aai

    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not key:
        raise RuntimeError(
            "Set ASSEMBLYAI_API_KEY in env to use the assemblyai backend."
        )
    aai.settings.api_key = key

    # Language: explicit override via VLOW_AAI_LANGUAGE, otherwise let
    # AssemblyAI auto-detect (set language_code=None, language_detection=True).
    lang = os.environ.get("VLOW_AAI_LANGUAGE")
    if lang:
        _config = aai.TranscriptionConfig(
            speech_models=MODELS,
            language_code=lang,
        )
    else:
        _config = aai.TranscriptionConfig(
            speech_models=MODELS,
            language_detection=True,
        )
    return _config


def warmup() -> None:
    # No network — just import the SDK and verify the API key is set so a
    # missing key fails fast at app startup instead of mid-dictation.
    _get_config()


def transcribe(audio: np.ndarray) -> str:
    if audio.size < MIN_SAMPLES:
        return ""
    import assemblyai as aai

    config = _get_config()
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
