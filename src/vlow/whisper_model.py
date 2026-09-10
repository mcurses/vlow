"""The on-device Whisper model: is it here, how big is it, fetch it with progress.

mlx-whisper resolves the model through the Hugging Face cache
(~/.cache/huggingface/hub). Nothing here downloads implicitly — the app asks
the user first (Settings → On-device model → Download) so a fresh install
never pulls 3 GB behind their back.
"""

import threading
import time
from pathlib import Path
from typing import Callable

from huggingface_hub import HfApi, constants as hf_constants, snapshot_download
from huggingface_hub.utils import tqdm as hf_tqdm

MODEL = "mlx-community/whisper-large-v3-mlx"
DISPLAY_NAME = "Whisper large-v3"
APPROX_BYTES = 3_083_522_487  # weights.npz + config, as of 2026-09; refined at download time

StatusCallback = Callable[[dict], None]


class ModelNotDownloaded(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            f"{DISPLAY_NAME} is not downloaded yet — open Settings and click Download."
        )


def local_path() -> Path | None:
    """Snapshot directory if the model is fully present in the cache."""
    try:
        path = Path(snapshot_download(MODEL, local_files_only=True))
    except Exception:
        return None
    if not (path / "config.json").exists():
        return None
    if not any(path.glob("weights.*")):
        return None
    return path


def is_downloaded() -> bool:
    return local_path() is not None


def size_on_disk() -> int:
    path = local_path()
    if path is None:
        return 0
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file() or p.is_symlink())


def _gb(n: int | float) -> str:
    return f"{n / 1e9:.1f} GB"


# ---------------------------------------------------------------------------
# Download with progress
#
# snapshot_download builds one byte-counting bar from `tqdm_class` (unit="B")
# and funnels every file's progress into it — that is our hook. The bar is
# usually *disabled* (hf's log level), and a disabled tqdm skips most of its
# __init__, so we must remember the unit ourselves instead of reading
# self.unit. As a fallback, a poller sums the bytes landing in the repo's
# blobs/ folder. Whichever is larger wins.

_lock = threading.Lock()
_active: dict | None = None  # {"done": bytes, "total": bytes, "cb": callback, "last": ts}


def _blobs_dir() -> Path:
    return Path(hf_constants.HF_HUB_CACHE) / ("models--" + MODEL.replace("/", "--")) / "blobs"


def _bytes_in_cache() -> int:
    blobs = _blobs_dir()
    if not blobs.is_dir():
        return 0
    total = 0
    for p in blobs.iterdir():
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def _poll_disk(active: dict) -> None:
    while _active is active:
        on_disk = _bytes_in_cache()
        if on_disk > active["done"]:
            active["done"] = on_disk
            active["last"] = time.monotonic()
            active["cb"](status())
        time.sleep(0.5)


def status() -> dict:
    """{"state": missing|downloading|ready|error, "progress": 0..1, "detail": str}"""
    active = _active
    if active is not None:
        done, total = active["done"], max(active["total"], 1)
        return {
            "state": "downloading",
            "progress": min(done / total, 1.0),
            "detail": f"{_gb(done)} of {_gb(total)}",
        }
    if is_downloaded():
        return {"state": "ready", "progress": 1.0, "detail": f"Ready · {_gb(size_on_disk())} on disk"}
    return {"state": "missing", "progress": 0.0, "detail": f"Not downloaded · about {_gb(APPROX_BYTES)}"}


def is_downloading() -> bool:
    return _active is not None


class _Progress(hf_tqdm):
    """tqdm stand-in for huggingface_hub; only the byte bar is of interest."""

    def __init__(self, *args, **kwargs):
        self._counts_bytes = kwargs.get("unit") == "B"
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        result = super().update(n)
        active = _active
        if active is not None and self._counts_bytes and n:
            active["tqdm"] += n
            total = getattr(self, "total", None)
            if total and total > active["total"]:
                active["total"] = int(total)
            if active["tqdm"] > active["done"]:
                active["done"] = active["tqdm"]
                now = time.monotonic()
                if now - active["last"] >= 0.2:
                    active["last"] = now
                    active["cb"](status())
        return result


def _total_bytes() -> int:
    try:
        info = HfApi().model_info(MODEL, files_metadata=True)
        total = sum(s.size or 0 for s in info.siblings or [])
        return total or APPROX_BYTES
    except Exception:
        return APPROX_BYTES


def download(on_status: StatusCallback) -> None:
    """Blocking; run it on a worker thread. `on_status` gets status() dicts
    (throttled) from download threads, and a final ready/error one."""
    global _active
    with _lock:
        if _active is not None:
            return
        _active = {"done": 0, "tqdm": 0, "total": APPROX_BYTES, "cb": on_status, "last": 0.0}
    try:
        on_status(status())
        _active["total"] = _total_bytes()
        threading.Thread(target=_poll_disk, args=(_active,), daemon=True).start()
        snapshot_download(MODEL, tqdm_class=_Progress)
    except Exception as e:
        _active = None
        on_status({"state": "error", "progress": 0.0, "detail": f"Download failed: {e}"})
        raise
    _active = None
    on_status(status())
