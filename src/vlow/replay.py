import threading
import time
from typing import Callable

from pynput import keyboard

from .paste import paste


def validate_hotkey(spec: str) -> str:
    """Normalize a pynput hotkey spec such as ``<ctrl>+<cmd>+v``. Empty means
    "no shortcut". Raises ValueError for anything pynput can't parse or for
    a bare key without a modifier (which would swallow ordinary typing)."""
    spec = (spec or "").strip().lower()
    if not spec:
        return ""
    try:
        keys = keyboard.HotKey.parse(spec)
    except Exception as e:
        raise ValueError(f"repaste_hotkey {spec!r} is not a valid shortcut: {e}") from e
    modifiers = {
        keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
        keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
        keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    }
    if not any(k in modifiers for k in keys):
        raise ValueError("repaste_hotkey needs Control, Option or Command")
    if all(k in modifiers or k == keyboard.Key.shift for k in keys):
        raise ValueError("repaste_hotkey needs a non-modifier key")
    return spec


class ReplayHotkey:
    """Global shortcut that re-pastes the last transcription. The spec is a
    pynput hotkey string (``<ctrl>+<cmd>+v``); empty disables the shortcut."""

    def __init__(self, get_last: Callable[[], str], hotkey: str = "") -> None:
        self._get_last = get_last
        self._hotkey = validate_hotkey(hotkey)
        self._listener: keyboard.GlobalHotKeys | None = None
        self._busy = False

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def start(self) -> None:
        if not self._hotkey or self._listener is not None:
            return
        self._listener = keyboard.GlobalHotKeys({self._hotkey: self._on_trigger})
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def set_hotkey(self, hotkey: str) -> None:
        """Swap the shortcut live (used when Settings changes it)."""
        hotkey = validate_hotkey(hotkey)
        if hotkey == self._hotkey:
            return
        self.stop()
        self._hotkey = hotkey
        self.start()

    def _on_trigger(self) -> None:
        if self._busy:
            return
        text = self._get_last()
        if not text:
            return
        self._busy = True

        def run():
            try:
                # Give the user a moment to release the modifiers so the
                # synthesized Cmd+V doesn't combine with a still-held key.
                time.sleep(0.12)
                paste(text)
            finally:
                time.sleep(0.25)
                self._busy = False

        threading.Thread(target=run, daemon=True).start()
