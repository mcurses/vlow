"""User config loaded from ~/.config/vlow/config.toml (optional)."""

import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "vlow" / "config.toml"

_DEFAULTS = {
    "hotkey": "fn",
}


def load() -> dict:
    conf = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            conf.update(tomllib.load(f))
    return conf
