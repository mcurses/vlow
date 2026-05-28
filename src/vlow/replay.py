import threading
import time
from typing import Callable

from pynput import keyboard

from .paste import paste


class ReplayHotkey:
    """Global Ctrl+Cmd+V — re-paste the last transcription."""

    def __init__(self, get_last: Callable[[], str]) -> None:
        self._get_last = get_last
        self._listener: keyboard.GlobalHotKeys | None = None
        self._busy = False

    def start(self) -> None:
        self._listener = keyboard.GlobalHotKeys({"<ctrl>+<cmd>+v": self._on_trigger})
        self._listener.start()

    def _on_trigger(self) -> None:
        if self._busy:
            return
        text = self._get_last()
        if not text:
            return
        self._busy = True

        def run():
            try:
                # Give the user a moment to release Ctrl so the synthesized
                # Cmd+V doesn't combine with a still-held modifier.
                time.sleep(0.12)
                paste(text)
            finally:
                time.sleep(0.25)
                self._busy = False

        threading.Thread(target=run, daemon=True).start()
