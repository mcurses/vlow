"""On-device Parakeet TDT 0.6B v3 via parakeet-mlx.

Parakeet is a Conformer/TDT model rather than an encoder-decoder like Whisper:
several times faster on Apple Silicon, 25 European languages, no per-window
language token (so mixed German/English fares better), but also no
initial_prompt — known words are corrected after the fact instead.

Everything that touches the model runs on one dedicated worker thread. MLX
streams are thread-bound, and parakeet-mlx's greedy decoder fails with
"There is no Stream(gpu, 0) in current thread" when the model is first run on
one thread (the app's warmup) and then used from another (the app's
transcription worker). Funnelling load, warmup and decode through a single
thread sidesteps that for good; callers still block until the result is in.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

import mlx.core as mx
import numpy as np

from .config import known_words
from .known_words_fix import apply_known_words
from .local_models import MODELS, ModelNotDownloaded, is_downloaded, local_path

PARAKEET = MODELS["parakeet-tdt-0.6b-v3"]
MIN_SAMPLES = 1600
SAMPLE_RATE = 16000
# Conformer attention is quadratic in sequence length; anything longer than
# this is cut into overlapping chunks and merged on the overlap, the same way
# parakeet_mlx's own file transcribe() does.
CHUNK_SEC = 120.0
OVERLAP_SEC = 15.0

_T = TypeVar("_T")
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="parakeet")
_model = None  # only ever touched on the worker thread


def _on_worker(fn: Callable[[], _T]) -> _T:
    return _worker.submit(fn).result()


def _load():
    global _model
    if _model is None:
        from parakeet_mlx import from_pretrained

        path = local_path(PARAKEET)
        if path is None:
            raise ModelNotDownloaded(PARAKEET)
        # Local snapshot path, not the repo id: the bundle runs with the
        # Hugging Face hub in offline mode and must never fetch here.
        _model = from_pretrained(str(path), dtype=mx.bfloat16)
    return _model


def _generate(model, audio: np.ndarray):
    from parakeet_mlx.audio import get_logmel

    mel = get_logmel(mx.array(audio.astype(np.float32)), model.preprocessor_config)
    return model.generate(mel)[0]


def _generate_chunked(model, audio: np.ndarray):
    from parakeet_mlx import DecodingConfig
    from parakeet_mlx.alignment import (
        merge_longest_common_subsequence,
        merge_longest_contiguous,
        sentences_to_result,
        tokens_to_sentences,
    )

    chunk = int(CHUNK_SEC * SAMPLE_RATE)
    overlap = int(OVERLAP_SEC * SAMPLE_RATE)
    all_tokens: list = []
    for start in range(0, audio.size, chunk - overlap):
        end = min(start + chunk, audio.size)
        if end - start < model.preprocessor_config.hop_length:
            break  # a zero-length mel would crash the encoder
        result = _generate(model, audio[start:end])
        offset = start / SAMPLE_RATE
        for sentence in result.sentences:
            for token in sentence.tokens:
                token.start += offset
                token.end = token.start + token.duration
        if not all_tokens:
            all_tokens = result.tokens
            continue
        try:
            all_tokens = merge_longest_contiguous(
                all_tokens, result.tokens, overlap_duration=OVERLAP_SEC
            )
        except RuntimeError:
            all_tokens = merge_longest_common_subsequence(
                all_tokens, result.tokens, overlap_duration=OVERLAP_SEC
            )
    return sentences_to_result(tokens_to_sentences(all_tokens, DecodingConfig().sentence))


def _warmup_on_worker() -> None:
    model = _load()
    try:
        _generate(model, np.zeros(SAMPLE_RATE, dtype=np.float32))
    finally:
        mx.clear_cache()


def _transcribe_on_worker(audio: np.ndarray) -> str:
    model = _load()
    try:
        if audio.size / SAMPLE_RATE <= CHUNK_SEC:
            result = _generate(model, audio)
        else:
            result = _generate_chunked(model, audio)
    finally:
        # Same reasoning as transcribe_mlx._release_buffers: hand MLX's
        # between-dictation buffer cache back; the loaded weights stay put.
        mx.clear_cache()
    return result.text.strip()


def warmup() -> None:
    if not is_downloaded(PARAKEET):
        raise ModelNotDownloaded(PARAKEET)
    _on_worker(_warmup_on_worker)


def transcribe(audio: np.ndarray) -> str:
    if audio.size < MIN_SAMPLES:
        return ""
    if not is_downloaded(PARAKEET):
        raise ModelNotDownloaded(PARAKEET)
    text = _on_worker(lambda: _transcribe_on_worker(audio))
    return apply_known_words(text, known_words())
