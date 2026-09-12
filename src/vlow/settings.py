"""Central settings: ~/.config/vlow/config.toml is the source of truth.

The Settings window (settings_window.py → native/VlowSettings.swift) edits
these values; this module validates them, writes the file and mirrors the
env-backed keys into os.environ so the running app picks them up.
"""

import json
import os
from pathlib import Path

from .config import CONFIG_PATH, TOML_TO_ENV, load as load_config
from .hotkey import HOTKEYS
from .local_models import DEFAULT_MODEL, MODELS
from .replay import validate_hotkey
from .transcribe import DEFAULT_AUTO_THRESHOLD_SEC, VALID_BACKENDS

VALID_MODES = ("toggle", "ptt")

# Everything the Settings window shows, with the value a fresh install gets.
DEFAULTS: dict = {
    "hotkey": "fn",
    "mode": "toggle",
    "repaste_hotkey": "",  # pynput spec, e.g. "<ctrl>+<cmd>+v"; empty = off
    "paste_to_origin_app": True,  # batch mode: paste into the app that was frontmost at start
    "backend": "mlx",
    "local_model": DEFAULT_MODEL,
    "auto_threshold_sec": DEFAULT_AUTO_THRESHOLD_SEC,
    "assemblyai_api_key": "",
    "aai_language": "",
    "known_words": ["vlow"],
    "check_updates": True,
}

_HEADER = """\
# vlow configuration — edited by the Settings window (menubar → Settings…).
# Values here take precedence over .env and environment variables.
"""


def current() -> dict:
    """Effective values as the Settings window should display them."""
    conf = load_config()  # merges config.toml over .env / env into os.environ
    out = {}
    for key, default in DEFAULTS.items():
        env_key = TOML_TO_ENV.get(key)
        if env_key:
            value = os.environ.get(env_key)
            if value is None or value == "":
                value = conf.get(key, default)
        else:
            value = conf.get(key, default)
        out[key] = value
    out = normalize(out)
    out["config_path"] = str(CONFIG_PATH)
    # The window renders the model picker and download rows from this list,
    # so Python stays the single source of truth for names and sizes.
    out["local_models"] = [
        {
            "key": m.key,
            "name": m.display,
            "size": f"About {m.approx_bytes / 1e9:.1f} GB",
            "blurb": m.blurb,
        }
        for m in MODELS.values()
    ]
    from .updater import current_version  # local import: updater pulls in AppKit lazily

    out["app_version"] = current_version()
    return out


def normalize(data: dict) -> dict:
    """Coerce + validate a settings dict (from the UI or from disk)."""
    out = {}
    hotkey = str(data.get("hotkey") or DEFAULTS["hotkey"])
    if hotkey not in HOTKEYS:
        raise ValueError(f"hotkey must be one of {', '.join(HOTKEYS)}, got {hotkey!r}")
    out["hotkey"] = hotkey

    mode = str(data.get("mode") or DEFAULTS["mode"])
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    out["mode"] = mode

    out["repaste_hotkey"] = validate_hotkey(str(data.get("repaste_hotkey") or ""))

    raw = data.get("paste_to_origin_app", DEFAULTS["paste_to_origin_app"])
    out["paste_to_origin_app"] = raw if isinstance(raw, bool) else str(raw).lower() in ("1", "true", "yes")

    backend = str(data.get("backend") or DEFAULTS["backend"]).lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(f"backend must be one of {VALID_BACKENDS}, got {backend!r}")
    out["backend"] = backend

    local_model = str(data.get("local_model") or DEFAULTS["local_model"]).lower()
    if local_model not in MODELS:
        raise ValueError(f"local_model must be one of {tuple(MODELS)}, got {local_model!r}")
    out["local_model"] = local_model

    raw = data.get("auto_threshold_sec", DEFAULTS["auto_threshold_sec"])
    try:
        threshold = float(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"auto_threshold_sec must be a number, got {raw!r}") from e
    if threshold <= 0:
        raise ValueError("auto_threshold_sec must be positive")
    out["auto_threshold_sec"] = threshold

    out["assemblyai_api_key"] = str(data.get("assemblyai_api_key") or "").strip()
    out["aai_language"] = str(data.get("aai_language") or "").strip().lower()

    words: list[str] = []
    for w in data.get("known_words") or []:
        w = str(w).strip()
        if w and w not in words:
            words.append(w)
    out["known_words"] = words

    raw = data.get("check_updates", DEFAULTS["check_updates"])
    out["check_updates"] = raw if isinstance(raw, bool) else str(raw).lower() in ("1", "true", "yes")
    return out


def apply_env(data: dict) -> None:
    """Mirror the env-backed keys into os.environ (empty → unset)."""
    for key, env_key in TOML_TO_ENV.items():
        value = data.get(key)
        if value is None or value == "":
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = _env_str(value)


def _env_str(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def save(data: dict, path: Path = CONFIG_PATH) -> None:
    """Write config.toml atomically (tmp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(_HEADER + to_toml(data))
    tmp.chmod(0o600)  # may hold the AssemblyAI key
    os.replace(tmp, path)


def ensure_config_file(path: Path = CONFIG_PATH) -> bool:
    """First launch: create config.toml seeded from whatever is effective now
    (.env / env vars) plus the one example known word. Returns True if the
    file was created."""
    if path.exists():
        return False
    save(current(), path)
    return True


def to_toml(data: dict) -> str:
    """Serialize our flat schema (strings, numbers, string lists)."""
    lines = []
    for key in DEFAULTS:
        if key not in data:
            continue
        lines.append(f"{key} = {_toml_value(data[key])}")
    return "\n".join(lines) + "\n"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        inner = ",\n".join(f"    {_toml_value(v)}" for v in value)
        return f"[\n{inner},\n]"
    # TOML basic strings share JSON's escaping rules for our content.
    return json.dumps(str(value), ensure_ascii=False)
