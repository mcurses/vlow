"""The on-device models: which exist, which one is selected, are they here,
how big are they, fetch them with progress.

Both models resolve through the Hugging Face cache (~/.cache/huggingface/hub).
Nothing here downloads implicitly — the app asks the user first (Settings →
On-device model → Download) so a fresh install never pulls gigabytes behind
their back.
"""

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from huggingface_hub import HfApi, constants as hf_constants, snapshot_download
from huggingface_hub.utils import tqdm as hf_tqdm


@dataclass(frozen=True)
class LocalModel:
    key: str  # value in config.toml / VLOW_LOCAL_MODEL
    repo: str  # Hugging Face repo
    display: str
    approx_bytes: int  # refined at download time
    weight_glob: str  # a file matching this proves the weights are present
    module: str  # vlow module implementing warmup()/transcribe()
    blurb: str  # one line for the Settings footer


MODELS: dict[str, LocalModel] = {
    m.key: m
    for m in (
        LocalModel(
            key="whisper-large-v3",
            repo="mlx-community/whisper-large-v3-mlx",
            display="Whisper large-v3",
            approx_bytes=3_083_522_487,
            weight_glob="weights.*",
            module="transcribe_mlx",
            blurb=(
                "99 languages, the safer pick for monolingual German. Commits to one "
                "language per 30-second window, so mixed German/English suffers."
            ),
        ),
        LocalModel(
            key="parakeet-tdt-0.6b-v3",
            repo="mlx-community/parakeet-tdt-0.6b-v3",
            display="Parakeet TDT 0.6B v3",
            approx_bytes=2_508_742_000,
            weight_glob="model.safetensors",
            module="transcribe_parakeet",
            blurb=(
                "25 European languages, several times faster, and better on mixed "
                "German/English. No prompt biasing: known words are matched after the fact."
            ),
        ),
    )
}
DEFAULT_MODEL = "whisper-large-v3"

StatusCallback = Callable[[dict], None]


class ModelNotDownloaded(RuntimeError):
    def __init__(self, model: LocalModel) -> None:
        self.model = model
        super().__init__(
            f"{model.display} is not downloaded yet — open Settings and click Download."
        )


def selected_key() -> str:
    key = (os.environ.get("VLOW_LOCAL_MODEL") or DEFAULT_MODEL).lower()
    if key not in MODELS:
        raise ValueError(f"VLOW_LOCAL_MODEL={key!r} not in {tuple(MODELS)}")
    return key


def selected() -> LocalModel:
    return MODELS[selected_key()]


def local_path(model: LocalModel) -> Path | None:
    """Snapshot directory if the model is fully present in the cache."""
    try:
        path = Path(snapshot_download(model.repo, local_files_only=True))
    except Exception:
        return None
    if not (path / "config.json").exists():
        return None
    if not any(path.glob(model.weight_glob)):
        return None
    return path


def is_downloaded(model: LocalModel) -> bool:
    return local_path(model) is not None


def _repo_cache_dir(model: LocalModel) -> Path:
    return Path(hf_constants.HF_HUB_CACHE) / ("models--" + model.repo.replace("/", "--"))


def remove(model: LocalModel) -> int:
    """Delete the model from the Hugging Face cache (blobs, snapshots, refs —
    the whole models--org--repo directory). Returns the bytes freed. Refuses
    while that model is downloading."""
    import shutil

    active = _active
    if active is not None and active["model"] == model.key:
        raise RuntimeError(f"{model.display} is downloading — wait for it to finish.")
    repo_dir = _repo_cache_dir(model)
    if not repo_dir.exists():
        return 0
    freed = sum(p.stat().st_size for p in repo_dir.rglob("*") if p.is_file())
    shutil.rmtree(repo_dir)
    return freed


def size_on_disk(model: LocalModel) -> int:
    path = local_path(model)
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
#
# The hf_xet fast path is switched off for the download: measured on the
# 3 GB Whisper weights it reported nothing for ~250 s and only wrote the file
# at the very end, so the user would stare at an idle bar. The plain HTTP
# path streams into blobs/*.incomplete and ticks the bar per chunk.
#
# One download at a time: the tqdm hook is process-global, so two concurrent
# snapshots could not be told apart.

_lock = threading.Lock()
_active: dict | None = None  # {"model": key, "done", "total", "tqdm", "cb", "last"}


def _blobs_dir(model: LocalModel) -> Path:
    return Path(hf_constants.HF_HUB_CACHE) / ("models--" + model.repo.replace("/", "--")) / "blobs"


def _bytes_in_cache(model: LocalModel) -> int:
    blobs = _blobs_dir(model)
    if not blobs.is_dir():
        return 0
    total = 0
    for p in blobs.iterdir():
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def _poll_disk(active: dict, model: LocalModel) -> None:
    while _active is active:
        on_disk = _bytes_in_cache(model)
        if on_disk > active["done"]:
            active["done"] = on_disk
            active["last"] = time.monotonic()
            active["cb"](status(model))
        time.sleep(0.5)


def status(model: LocalModel) -> dict:
    """{"model": key, "state": missing|downloading|ready|error, "progress": 0..1, "detail": str}"""
    active = _active
    if active is not None and active["model"] == model.key:
        done, total = active["done"], max(active["total"], 1)
        return {
            "model": model.key,
            "state": "downloading",
            "progress": min(done / total, 1.0),
            "detail": f"{_gb(done)} of {_gb(total)}",
        }
    if is_downloaded(model):
        return {
            "model": model.key,
            "state": "ready",
            "progress": 1.0,
            "detail": f"Ready · {_gb(size_on_disk(model))} on disk",
        }
    return {
        "model": model.key,
        "state": "missing",
        "progress": 0.0,
        "detail": f"Not downloaded · about {_gb(model.approx_bytes)}",
    }


def all_status() -> list[dict]:
    return [status(m) for m in MODELS.values()]


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
                    active["cb"](status(MODELS[active["model"]]))
        return result


def _total_bytes(model: LocalModel) -> int:
    try:
        info = HfApi().model_info(model.repo, files_metadata=True)
        total = sum(s.size or 0 for s in info.siblings or [])
        return total or model.approx_bytes
    except Exception:
        return model.approx_bytes


def download(model: LocalModel, on_status: StatusCallback) -> None:
    """Blocking; run it on a worker thread. `on_status` gets status() dicts
    (throttled) from download threads, and a final ready/error one. Returns
    immediately if another download is already running."""
    global _active
    with _lock:
        if _active is not None:
            return
        _active = {
            "model": model.key,
            "done": 0,
            "tqdm": 0,
            "total": model.approx_bytes,
            "cb": on_status,
            "last": 0.0,
        }
    xet_was_disabled = hf_constants.HF_HUB_DISABLE_XET
    hf_constants.HF_HUB_DISABLE_XET = True
    # The LaunchAgent pins HF_HUB_OFFLINE=1 so warmup never blocks on a hub
    # round-trip that hangs forever under launchd (see login_item.py).
    # A deliberate download is the one moment we do want the network, so lift
    # it for the duration: the module constant for code that already imported
    # huggingface_hub, the env vars for anything importing it mid-download.
    offline_was = hf_constants.HF_HUB_OFFLINE
    env_was = {k: os.environ.pop(k, None) for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
    hf_constants.HF_HUB_OFFLINE = False
    try:
        on_status(status(model))
        _active["total"] = _total_bytes(model)
        threading.Thread(target=_poll_disk, args=(_active, model), daemon=True).start()
        snapshot_download(model.repo, tqdm_class=_Progress)
    except Exception as e:
        _active = None
        on_status(
            {
                "model": model.key,
                "state": "error",
                "progress": 0.0,
                "detail": f"Download failed: {e}",
            }
        )
        raise
    finally:
        hf_constants.HF_HUB_DISABLE_XET = xet_was_disabled
        hf_constants.HF_HUB_OFFLINE = offline_was
        for k, v in env_was.items():
            if v is not None:
                os.environ[k] = v
    _active = None
    on_status(status(model))
