"""Runtime diagnostics so a wedged instance can be debugged from the outside.

Born from a 2026-08-05 incident: the menubar icon was visible but clicking it
did nothing, the hotkey was dead, and the process looked healthy at the native
level (all threads idle). Without Python-level stacks or a liveness trail in
the logs there was nothing to go on. Three tools fix that:

- ``kill -USR1 <pid>`` appends every Python thread's stack to vlow.err.
- A watchdog thread pings the main runloop once a minute and periodically
  logs a heartbeat: app state, status-item health, and whether modifier-key
  events are still arriving. If the main runloop stops servicing pings while
  the app is idle, it dumps stacks and exits non-zero so launchd relaunches.
- Sleep/wake/session-switch notifications are logged so a wedge can be
  correlated with power events.
"""

import faulthandler
import os
import signal
import sys
import threading
import time
from typing import Callable

from AppKit import NSWorkspace
from Foundation import NSObject


def _log(msg: str) -> None:
    print(f"[vlow {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def install_signal_dump() -> None:
    """SIGUSR1 → dump all Python thread stacks to stderr (vlow.err).

    Also enables faulthandler for fatal signals (SIGSEGV etc.).
    """
    faulthandler.enable()
    faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)


_POWER_NOTIFICATIONS = [
    "NSWorkspaceWillSleepNotification",
    "NSWorkspaceDidWakeNotification",
    "NSWorkspaceScreensDidSleepNotification",
    "NSWorkspaceScreensDidWakeNotification",
    "NSWorkspaceSessionDidBecomeActiveNotification",
    "NSWorkspaceSessionDidResignActiveNotification",
]

_power_logger = None  # keep the observer alive


class _PowerLogger(NSObject):
    def note_(self, notification):
        _log(f"power: {notification.name()}")


def install_power_logging() -> None:
    global _power_logger
    _power_logger = _PowerLogger.alloc().init()
    center = NSWorkspace.sharedWorkspace().notificationCenter()
    for name in _POWER_NOTIFICATIONS:
        center.addObserver_selector_name_object_(_power_logger, b"note:", name, None)


class Watchdog(threading.Thread):
    """Ping the main runloop; log heartbeats; self-heal on a wedged runloop.

    - Every PING_INTERVAL a block is queued on the main NSOperationQueue.
      If it doesn't run within PING_TIMEOUT the main runloop isn't draining.
    - Every LOG_EVERY successful pings a heartbeat line is logged with the
      probe result (app state, status-item window, hotkey event counters).
    - After STALL_LIMIT consecutive missed pings *while the app is idle*,
      stacks are dumped and the process exits 86 — launchd's KeepAlive
      restarts it. Never fires mid-recording/-transcription.
    """

    PING_INTERVAL = 60.0
    PING_TIMEOUT = 10.0
    LOG_EVERY = 5
    STALL_LIMIT = 3

    def __init__(
        self,
        on_main: Callable[[Callable[[], None]], None],
        probe_main: Callable[[], str],
        get_state: Callable[[], str],
        is_idle: Callable[[], bool],
    ) -> None:
        super().__init__(daemon=True, name="vlow-watchdog")
        self._on_main = on_main
        self._probe_main = probe_main
        self._get_state = get_state
        self._is_idle = is_idle

    def run(self) -> None:
        tick = 0
        stalls = 0
        while True:
            time.sleep(self.PING_INTERVAL)
            tick += 1
            answered = threading.Event()
            result: dict[str, str] = {}

            def pong(answered=answered, result=result) -> None:
                try:
                    result["info"] = self._probe_main()
                except Exception as e:
                    result["info"] = f"probe failed: {e}"
                answered.set()

            self._on_main(pong)
            if answered.wait(self.PING_TIMEOUT):
                if stalls:
                    _log(f"watchdog: main runloop recovered after {stalls} missed ping(s)")
                stalls = 0
                if tick % self.LOG_EVERY == 0:
                    _log(f"heartbeat: state={self._get_state()} {result.get('info', '')}")
                continue

            stalls += 1
            _log(
                f"watchdog: main runloop did not service ping within "
                f"{self.PING_TIMEOUT:.0f}s (miss {stalls}/{self.STALL_LIMIT}, "
                f"state={self._get_state()}) — dumping all thread stacks"
            )
            faulthandler.dump_traceback(all_threads=True)
            if stalls >= self.STALL_LIMIT and self._is_idle():
                _log("watchdog: main runloop wedged while idle — exiting 86 so launchd restarts vlow")
                os._exit(86)
