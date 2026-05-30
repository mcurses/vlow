"""Push-to-talk streaming via AssemblyAI Universal Streaming.

Mic frames flow callback → queue → generator → SDK WebSocket.
Turn events surface to caller-supplied on_partial / on_final callbacks.
Final accumulated text is returned by stop().
"""

import os
import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1600  # 100 ms at 16 kHz
SPEECH_MODEL = "u3-rt-pro"


class StreamingSession:
    def __init__(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_partial = on_partial or (lambda _: None)
        self._on_final = on_final or (lambda _: None)
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._final_parts: list[str] = []
        self._client = None
        self._stream: Optional[sd.InputStream] = None
        self._pump_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        from assemblyai.streaming.v3 import (
            StreamingClient,
            StreamingClientOptions,
            StreamingEvents,
            StreamingParameters,
        )

        key = os.environ.get("ASSEMBLYAI_API_KEY")
        if not key:
            raise RuntimeError(
                "ASSEMBLYAI_API_KEY required for ptt streaming."
            )

        self._client = StreamingClient(StreamingClientOptions(api_key=key))
        self._client.on(StreamingEvents.Turn, self._on_turn)
        self._client.on(StreamingEvents.Error, self._on_error)
        self._client.connect(
            StreamingParameters(
                sample_rate=SAMPLE_RATE,
                speech_model=SPEECH_MODEL,
                format_turns=True,
            )
        )

        # Audio capture → queue. dtype=int16 because AAI wants raw PCM16.
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SAMPLES,
            callback=self._audio_cb,
        )
        self._stream.start()

        # client.stream(iter) blocks the calling thread reading the iterator,
        # so run it in the background.
        self._pump_thread = threading.Thread(target=self._pump, daemon=True)
        self._pump_thread.start()

    def _audio_cb(self, indata: np.ndarray, frames, time_info, status) -> None:
        self._queue.put(bytes(indata))

    def _pump(self) -> None:
        def gen():
            while True:
                chunk = self._queue.get()
                if chunk is None:
                    return
                yield chunk

        try:
            self._client.stream(gen())
        except Exception as e:
            print(f"[stream_aai] pump error: {e}", flush=True)

    def _on_turn(self, _client, event) -> None:
        text = (event.transcript or "").strip()
        if not text:
            return
        if getattr(event, "end_of_turn", False):
            self._final_parts.append(text)
            self._on_final(text)
        else:
            self._on_partial(text)

    def _on_error(self, _client, error) -> None:
        print(f"[stream_aai] error: {error}", flush=True)

    def stop(self) -> str:
        # Order matters: stop the mic so no new chunks queue; sentinel-close
        # the generator; then terminate the SDK session (which flushes finals).
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

        self._queue.put(None)

        if self._client is not None:
            try:
                self._client.disconnect(terminate=True)
            except Exception as e:
                print(f"[stream_aai] disconnect error: {e}", flush=True)
            finally:
                self._client = None

        if self._pump_thread is not None:
            self._pump_thread.join(timeout=2.0)
            self._pump_thread = None

        return " ".join(self._final_parts).strip()
