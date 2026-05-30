import os
import threading
import time
from typing import Callable, Optional

from Cocoa import NSEvent

NSEventMaskFlagsChanged = 1 << 12

HOTKEYS = {
    "fn":        (63, 1 << 23),  # NSEventModifierFlagFunction
    "right_cmd": (54, 1 << 20),  # NSEventModifierFlagCommand
    "right_opt": (61, 1 << 19),  # NSEventModifierFlagOption
    "left_opt":  (58, 1 << 19),  # NSEventModifierFlagOption
}
DEFAULT_HOTKEY = "fn"

DEBUG = bool(os.environ.get("VLOW_DEBUG"))


class DoubleTapDetector:
    """Detect a double-tap of a modifier key (configurable).

    Uses BOTH a global and a local NSEvent monitor — the global one fires while
    other apps are active (the common case for a menubar app), the local one
    covers the rare moments our own process is the active app (e.g. just after
    a system permission prompt).

    Requires Accessibility permission for the host process.
    """

    def __init__(
        self,
        callback: Callable[[], None],
        hotkey: str = DEFAULT_HOTKEY,
        threshold_sec: float = 0.35,
    ) -> None:
        if hotkey not in HOTKEYS:
            raise ValueError(
                f"Unknown hotkey {hotkey!r}. Choose from: {', '.join(HOTKEYS)}"
            )
        self._keycode, self._mask = HOTKEYS[hotkey]
        self._hotkey_name = hotkey
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
        if event.keyCode() != self._keycode:
            return
        pressed = bool(event.modifierFlags() & self._mask)
        if DEBUG:
            gap = time.monotonic() - self._last_press
            print(
                f"[hotkey] {self._hotkey_name} {'down' if pressed else 'up'} "
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


class TapHoldDetector:
    """Distinguish a double-tap from a press-and-hold on one modifier key.

    Fires on_double_tap when the user taps twice within `dt_threshold`.
    Fires on_hold_start when the key is held continuously for `hold_threshold`
    (when it can no longer be the first half of a double-tap). on_hold_end
    fires on the matching release. A single quick tap that never pairs with
    a second produces no callback.
    """

    def __init__(
        self,
        on_double_tap: Callable[[], None],
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[], None],
        hotkey: str = DEFAULT_HOTKEY,
        dt_threshold: float = 0.35,
        hold_threshold: float = 0.30,
    ) -> None:
        if hotkey not in HOTKEYS:
            raise ValueError(
                f"Unknown hotkey {hotkey!r}. Choose from: {', '.join(HOTKEYS)}"
            )
        self._keycode, self._mask = HOTKEYS[hotkey]
        self._hotkey_name = hotkey
        self._on_double_tap = on_double_tap
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end
        self._dt_threshold = dt_threshold
        self._hold_threshold = hold_threshold
        self._lock = threading.Lock()
        # states: idle | pressed | released | held | doubletap
        self._state = "idle"
        self._first_press_time = 0.0
        self._was_pressed = False
        self._hold_timer: Optional[threading.Timer] = None
        self._dt_timer: Optional[threading.Timer] = None
        self._global_monitor = None
        self._local_monitor = None

    def start(self) -> None:
        self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._handle
        )
        self._local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._handle_local
        )

    def stop(self) -> None:
        for m in (self._global_monitor, self._local_monitor):
            if m is not None:
                NSEvent.removeMonitor_(m)
        self._global_monitor = None
        self._local_monitor = None
        with self._lock:
            self._cancel_timers_locked()

    def _handle_local(self, event):
        self._handle(event)
        return event

    def _handle(self, event) -> None:
        if event.keyCode() != self._keycode:
            return
        pressed = bool(event.modifierFlags() & self._mask)
        if DEBUG:
            print(
                f"[hotkey-th] {self._hotkey_name} {'down' if pressed else 'up'} "
                f"state={self._state}",
                flush=True,
            )
        if pressed and not self._was_pressed:
            self._was_pressed = True
            self._on_physical_press()
        elif not pressed and self._was_pressed:
            self._was_pressed = False
            self._on_physical_release()

    def _on_physical_press(self) -> None:
        now = time.monotonic()
        fire_double_tap = False
        with self._lock:
            if self._state == "released" and now - self._first_press_time < self._dt_threshold:
                self._cancel_timers_locked()
                self._state = "doubletap"
                fire_double_tap = True
            else:
                self._cancel_timers_locked()
                self._state = "pressed"
                self._first_press_time = now
                self._hold_timer = threading.Timer(self._hold_threshold, self._hold_timeout)
                self._hold_timer.daemon = True
                self._hold_timer.start()
        if fire_double_tap:
            self._fire(self._on_double_tap)

    def _on_physical_release(self) -> None:
        fire_hold_end = False
        with self._lock:
            if self._state == "pressed":
                # released before hold threshold → may be first of a double-tap
                self._cancel_timers_locked()
                self._state = "released"
                self._dt_timer = threading.Timer(self._dt_threshold, self._dt_timeout)
                self._dt_timer.daemon = True
                self._dt_timer.start()
            elif self._state == "held":
                self._state = "idle"
                fire_hold_end = True
            elif self._state == "doubletap":
                self._state = "idle"
        if fire_hold_end:
            self._fire(self._on_hold_end)

    def _hold_timeout(self) -> None:
        fire = False
        with self._lock:
            if self._state == "pressed":
                self._state = "held"
                fire = True
        if fire:
            self._fire(self._on_hold_start)

    def _dt_timeout(self) -> None:
        with self._lock:
            if self._state == "released":
                self._state = "idle"

    def _cancel_timers_locked(self) -> None:
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None
        if self._dt_timer is not None:
            self._dt_timer.cancel()
            self._dt_timer = None

    def _fire(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as e:
            print(f"hotkey callback error: {e}", flush=True)


class HoldDetector:
    """Fire on_press / on_release for a single modifier key — push-to-talk.

    Uses the same global+local NSEvent monitor pair as DoubleTapDetector so
    presses are seen regardless of which app is active.
    """

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        hotkey: str = DEFAULT_HOTKEY,
    ) -> None:
        if hotkey not in HOTKEYS:
            raise ValueError(
                f"Unknown hotkey {hotkey!r}. Choose from: {', '.join(HOTKEYS)}"
            )
        self._keycode, self._mask = HOTKEYS[hotkey]
        self._hotkey_name = hotkey
        self._on_press = on_press
        self._on_release = on_release
        self._was_pressed = False
        self._global_monitor = None
        self._local_monitor = None

    def start(self) -> None:
        self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskFlagsChanged, self._handle
        )
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
        if event.keyCode() != self._keycode:
            return
        pressed = bool(event.modifierFlags() & self._mask)
        if DEBUG:
            print(
                f"[hotkey-ptt] {self._hotkey_name} {'down' if pressed else 'up'}",
                flush=True,
            )
        if pressed and not self._was_pressed:
            self._was_pressed = True
            try:
                self._on_press()
            except Exception as e:
                print(f"on_press error: {e}", flush=True)
        elif not pressed and self._was_pressed:
            self._was_pressed = False
            try:
                self._on_release()
            except Exception as e:
                print(f"on_release error: {e}", flush=True)
