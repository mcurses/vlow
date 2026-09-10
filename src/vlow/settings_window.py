"""PyObjC side of the Settings window (native/VlowSettings.swift)."""

import ctypes
import json
import sys
import time
from typing import Callable

import objc
from Foundation import NSObject

from .resources import glass_dylib

_sink = None  # keeps the callback target alive while the window exists


class _SettingsSink(NSObject):
    """Receives the JSON the Swift window emits on every (debounced) change."""

    def initWithHandler_(self, handler):
        self = objc.super(_SettingsSink, self).init()
        if self is None:
            return None
        self._handler = handler
        return self

    def settingsChanged_(self, payload) -> None:
        try:
            self._handler(json.loads(str(payload)))
        except Exception as e:  # never let an exception unwind into AppKit
            print(
                f"[vlow {time.strftime('%H:%M:%S')}] settings change failed: {e}",
                file=sys.stderr,
                flush=True,
            )


def _cls():
    ctypes.CDLL(str(glass_dylib()))  # idempotent; OSError → run scripts/build-glass.sh
    return objc.lookUpClass("VlowSettings")


def open_settings(data: dict, on_change: Callable[[dict], None]) -> None:
    """Show the window with `data` and route every edit to `on_change`.
    Main thread only."""
    global _sink
    _sink = _SettingsSink.alloc().initWithHandler_(on_change)
    _cls().show_target_selector_(json.dumps(data), _sink, "settingsChanged:")


def update_settings(data: dict) -> None:
    """Push new values into an open window (no-op if it was never shown)."""
    _cls().update_(json.dumps(data))
