"""User config loaded from ~/.config/vlow/config.toml and .env (both optional)."""

import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "vlow" / "config.toml"
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

_DEFAULTS = {
    "hotkey": "fn",
    "mode": "toggle",  # "toggle" (double-tap) or "ptt" (hold-to-talk)
}


def load_dotenv() -> None:
    """Load .env from the project root into os.environ (won't overwrite existing vars)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
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
