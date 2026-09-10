"""User config loaded from ~/.config/vlow/config.toml and .env (both optional)."""

import os
import tomllib
from pathlib import Path

from .resources import dotenv_candidates

CONFIG_PATH = Path.home() / ".config" / "vlow" / "config.toml"

_DEFAULTS = {
    "hotkey": "fn",
    "mode": "toggle",  # "toggle" (double-tap) or "ptt" (hold-to-talk)
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


_TOML_TO_ENV = {
    "assemblyai_api_key": "ASSEMBLYAI_API_KEY",
    "backend": "VLOW_BACKEND",
    "auto_threshold_sec": "VLOW_AUTO_THRESHOLD_SEC",
    "aai_language": "VLOW_AAI_LANGUAGE",
}


def load() -> dict:
    load_dotenv()
    conf = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            conf.update(tomllib.load(f))
    # Mirror selected config.toml keys to env vars (other modules read
    # os.environ). setdefault keeps shell env winning over .env / config.toml.
    for toml_key, env_key in _TOML_TO_ENV.items():
        if toml_key in conf:
            os.environ.setdefault(env_key, str(conf[toml_key]))
    return conf
