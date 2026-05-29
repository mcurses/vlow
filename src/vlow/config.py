"""User config loaded from ~/.config/vlow/config.toml and .env (both optional)."""

import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "vlow" / "config.toml"
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

_DEFAULTS = {
    "hotkey": "fn",
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


def load() -> dict:
    load_dotenv()
    conf = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            conf.update(tomllib.load(f))
    return conf
