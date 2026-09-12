"""User config: ~/.config/vlow/config.toml (edited by the Settings window)
with .env / environment variables as fallbacks for keys it doesn't set."""

import os
import tomllib
from pathlib import Path

from .resources import dotenv_candidates

CONFIG_PATH = Path.home() / ".config" / "vlow" / "config.toml"

_DEFAULTS = {
    "hotkey": "fn",
    "mode": "toggle",  # "toggle" (double-tap) or "ptt" (hold-to-talk)
    "repaste_hotkey": "",  # global shortcut for Re-paste Last; empty = none
    "paste_to_origin_app": True,  # batch: deliver text to the app that was frontmost at start
    "known_words": [],  # bias all backends toward these names/terms
}


def known_words() -> list[str]:
    """Return the configured list of names / terms to bias transcription
    toward. Always re-reads config so users can edit config.toml without
    restarting (relevant for streaming which constructs config per session)."""
    conf = load()
    raw = conf.get("known_words") or []
    return [str(w).strip() for w in raw if str(w).strip()]


def load_dotenv() -> None:
    """Load .env files into os.environ (won't overwrite existing vars).

    Checked in order: the repo root (dev checkout), then ~/.config/vlow/.env
    (the release bundle has no repo). setdefault keeps the first hit."""
    for path in dotenv_candidates():
        if path.exists():
            _load_env_file(path)


def _load_env_file(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key or not _:
            continue
        os.environ.setdefault(key, value)


TOML_TO_ENV = {
    "assemblyai_api_key": "ASSEMBLYAI_API_KEY",
    "backend": "VLOW_BACKEND",
    "local_model": "VLOW_LOCAL_MODEL",
    "auto_threshold_sec": "VLOW_AUTO_THRESHOLD_SEC",
    "aai_language": "VLOW_AAI_LANGUAGE",
}


def load() -> dict:
    load_dotenv()
    conf = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            conf.update(tomllib.load(f))
    # Mirror the env-backed keys into os.environ (other modules read that).
    # config.toml is the central config, so a key it sets overrides .env and
    # the shell; keys it leaves out fall back to whatever the environment has.
    for toml_key, env_key in TOML_TO_ENV.items():
        if toml_key not in conf:
            continue
        value = conf[toml_key]
        if value is None or value == "":
            os.environ.pop(env_key, None)
        else:
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            os.environ[env_key] = str(value)
    return conf
