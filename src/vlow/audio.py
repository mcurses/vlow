import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def refresh_devices() -> None:
    """Re-init PortAudio so newly-attached devices (e.g. just-connected
    Bluetooth headsets) show up. sounddevice's device list is otherwise
    a snapshot taken at first import."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception as e:
        print(f"[audio] refresh failed: {e}", flush=True)


def list_input_devices() -> list[dict]:
    """Return all currently-visible input devices.

    Each entry: {'index': int, 'name': str, 'is_default': bool}.
    Calls refresh_devices() first so a freshly-plugged mic shows up.
    """
    refresh_devices()
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    out: list[dict] = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            out.append({
                "index": i,
                "name": d["name"],
                "is_default": (i == default_in),
            })
    return out


def default_input_name() -> str:
    """Best-effort human-readable name for the current default input."""
    try:
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return "unknown"


class Recorder:
    def __init__(self, device: int | None = None) -> None:
        """device=None → follow whatever PortAudio reports as the default at
        start() time. Any int → that explicit device index."""
        self._device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def start(self) -> None:
        # Re-scan first so the BT mic that connected after launch is usable.
        refresh_devices()
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._cb,
            device=self._device,
        )
        self._stream.start()

    def _cb(self, indata, frames, time_info, status) -> None:
        self._chunks.append(indata.copy())

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks).flatten().astype(np.float32)
