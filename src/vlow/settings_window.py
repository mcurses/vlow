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

    def initWithHandler_action_(self, handler, on_action):
        self = objc.super(_SettingsSink, self).init()
        if self is None:
            return None
        self._handler = handler
        self._on_action = on_action
        return self

    def settingsAction_(self, name) -> None:
        try:
            self._on_action(str(name))
        except Exception as e:
            print(
                f"[vlow {time.strftime('%H:%M:%S')}] settings action {name} failed: {e}",
                file=sys.stderr,
                flush=True,
            )

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


def open_settings(
    data: dict,
    on_change: Callable[[dict], None],
    on_action: Callable[[str], None] = lambda name: None,
) -> None:
    """Show the window with `data`; every edit goes to `on_change`, button
    presses (e.g. "downloadModel") to `on_action`. Main thread only."""
    global _sink
    _sink = _SettingsSink.alloc().initWithHandler_action_(on_change, on_action)
    _cls().show_target_selector_actionSelector_(
        json.dumps(data), _sink, "settingsChanged:", "settingsAction:"
    )


def set_model_status(status: dict) -> None:
    """Update one on-device model row: {"model", "state", "progress", "detail"}."""
    _cls().setModelStatus_(json.dumps(status))


def update_settings(data: dict) -> None:
    """Push new values into an open window (no-op if it was never shown)."""
    _cls().update_(json.dumps(data))


def set_update_status(text: str) -> None:
    """Caption under the Updates row ("Checking…", "You're up to date", …)."""
    _cls().setUpdateStatus_(text)
