import os
import time
from typing import Callable

from Cocoa import NSEvent

NSEventMaskFlagsChanged = 1 << 12
RIGHT_OPTION_KEYCODE = 61
NX_DEVICERALTKEYMASK = 0x40

DEBUG = bool(os.environ.get("VLOW_DEBUG"))


class DoubleTapDetector:
    """Detect a double-tap of the right Option key.

    Uses BOTH a global and a local NSEvent monitor — the global one fires while
    other apps are active (the common case for a menubar app), the local one
    covers the rare moments our own process is the active app (e.g. just after
    a system permission prompt).

    Requires Accessibility permission for the host process.
    """

    def __init__(self, callback: Callable[[], None], threshold_sec: float = 0.35) -> None:
        self._callback = callback
        self._threshold = threshold_sec
        self._last_press = 0.0
        self._was_pressed = False
        self._global_monitor = None
        self._local_monitor = None

    def start(self) -> None:
        self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._handle
        )
        # Local monitor must return the event (or None to swallow); we pass
        # through so other handlers still see right-option.
        self._local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._handle_local
        )

    def stop(self) -> None:
        for m in (self._global_monitor, self._local_monitor):
            if m is not None:
                NSEvent.removeMonitor_(m)
        self._global_monitor = None
        self._local_monitor = None

    def _handle_local(self, event):
        self._handle(event)
        return event

    def _handle(self, event) -> None:
        if event.keyCode() != RIGHT_OPTION_KEYCODE:
            return
        pressed = bool(event.modifierFlags() & NX_DEVICERALTKEYMASK)
        if DEBUG:
            gap = time.monotonic() - self._last_press
            print(
                f"[hotkey] rOpt {'down' if pressed else 'up'} "
                f"was={self._was_pressed} gap={gap:.2f}s",
                flush=True,
            )
        if pressed and not self._was_pressed:
            now = time.monotonic()
            if now - self._last_press < self._threshold:
                self._last_press = 0.0
                try:
                    self._callback()
                except Exception as e:
                    print(f"hotkey callback error: {e}", flush=True)
            else:
                self._last_press = now
        self._was_pressed = pressed
