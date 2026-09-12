import os
import subprocess
import time

import objc

from AppKit import (
    NSApplicationActivateIgnoringOtherApps,
    NSPasteboard,
    NSPasteboardItem,
    NSWorkspace,
    NSWorkspaceApplicationKey,
    NSWorkspaceDidActivateApplicationNotification,
)
from Foundation import NSObject
from Foundation import NSData
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

KEYCODE_V = 9

# How long to wait after Cmd+V before restoring the user's clipboard. The
# target app has to consume the paste on its main thread; too short and we
# restore before it's read our text, too long and the user notices the flicker.
POST_PASTE_WAIT_SEC = 0.15


def set_clipboard(text: str) -> None:
    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    proc.communicate(input=text.encode("utf-8"))


def synth_cmd_v() -> None:
    down = CGEventCreateKeyboardEvent(None, KEYCODE_V, True)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    up = CGEventCreateKeyboardEvent(None, KEYCODE_V, False)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)
    CGEventPost(kCGHIDEventTap, up)


def snapshot_clipboard() -> list[dict[str, bytes]]:
    """Capture every type of every item currently on the general pasteboard,
    so we can restore images, RTF, file URLs, etc. — not just plain text."""
    try:
        pb = NSPasteboard.generalPasteboard()
        items = pb.pasteboardItems() or []
        snap: list[dict[str, bytes]] = []
        for it in items:
            payload: dict[str, bytes] = {}
            for t in list(it.types() or []):
                data = it.dataForType_(t)
                if data is not None:
                    payload[str(t)] = bytes(data)
            if payload:
                snap.append(payload)
        return snap
    except Exception:
        return []


def restore_clipboard(snap: list[dict[str, bytes]]) -> None:
    try:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        if not snap:
            return
        new_items = []
        for payload in snap:
            item = NSPasteboardItem.alloc().init()
            for t, b in payload.items():
                ns_data = NSData.dataWithBytes_length_(b, len(b))
                item.setData_forType_(ns_data, t)
            new_items.append(item)
        pb.writeObjects_(new_items)
    except Exception:
        pass  # a restore failure must never surface as a paste failure


def paste(text: str) -> None:
    """One-shot paste that preserves the user's clipboard: snapshot → write
    our text → Cmd+V → wait for target to consume → restore snapshot."""
    snap = snapshot_clipboard()
    set_clipboard(text)
    time.sleep(0.05)
    synth_cmd_v()
    time.sleep(POST_PASTE_WAIT_SEC)
    restore_clipboard(snap)


def paste_no_restore(text: str) -> None:
    """Paste without touching the caller's snapshot — used inside streaming
    sessions where snapshot/restore is managed at session granularity to
    avoid flicker between chunks."""
    set_clipboard(text)
    time.sleep(0.05)
    synth_cmd_v()


# How long an app may take to become frontmost after we activate it, and
# how long to let it settle (become key) before the synthesized Cmd+V.
ACTIVATE_TIMEOUT_SEC = 1.5
ACTIVATE_SETTLE_SEC = 0.1


def frontmost_app():
    """The NSRunningApplication that owns the menu bar right now, or None."""
    try:
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def is_self(app) -> bool:
    """True when `app` is this vlow process (alerts and the Settings window
    make vlow the active app; it must never be a paste target)."""
    try:
        return app is not None and int(app.processIdentifier()) == os.getpid()
    except Exception:
        return False


class _ActivationObserver(NSObject):
    def initWithTracker_(self, tracker):
        self = objc.super(_ActivationObserver, self).init()
        if self is None:
            return None
        self._tracker = tracker
        return self

    def appActivated_(self, note) -> None:
        try:
            app = note.userInfo()[NSWorkspaceApplicationKey]
        except Exception:
            return
        if not is_self(app):
            self._tracker.last_other = app


class FrontmostTracker:
    """Remembers the most recent frontmost app that is not vlow, so a paste
    target can be chosen even while vlow itself is active (alert just
    dismissed, Settings window in front). Start on the main thread."""

    def __init__(self) -> None:
        self.last_other = None
        self._observer = None

    def start(self) -> None:
        front = frontmost_app()
        if not is_self(front):
            self.last_other = front
        self._observer = _ActivationObserver.alloc().initWithTracker_(self)
        NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
            self._observer, "appActivated:", NSWorkspaceDidActivateApplicationNotification, None
        )

    def target(self):
        """Where a transcription started now should be pasted: the frontmost
        app, unless that is vlow — then the app active before it."""
        front = frontmost_app()
        if not is_self(front):
            return front
        return self.last_other


def app_label(app) -> str:
    if app is None:
        return "none"
    try:
        return f"{app.localizedName()} (pid {app.processIdentifier()})"
    except Exception:
        return "unknown app"


def _is_frontmost(app) -> bool:
    cur = frontmost_app()
    return cur is not None and cur.processIdentifier() == app.processIdentifier()


def activate_and_wait(app, timeout: float = ACTIVATE_TIMEOUT_SEC) -> bool:
    """Bring `app` to the front and wait until macOS reports it frontmost.
    Call from a worker thread: NSWorkspace only learns about the switch
    while the main runloop is free to run."""
    if app is None or app.isTerminated():
        return False
    if _is_frontmost(app):
        return True
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_frontmost(app):
            return True
        time.sleep(0.01)
    return False


def paste_into(text: str, target, return_focus: bool = True) -> str:
    """Paste `text` into `target` (an NSRunningApplication captured when the
    recording started), then hand focus back to whatever the user is looking
    at now. Falls back to a plain paste into the current app when the target
    is gone or refuses to come forward. Blocking — run on a worker thread.
    Returns "direct" | "switched" | "fallback" for the log."""
    current = frontmost_app()
    if target is None or target.isTerminated() or is_self(target):
        paste(text)
        return "direct"
    if current is not None and current.processIdentifier() == target.processIdentifier():
        paste(text)
        return "direct"
    if not activate_and_wait(target):
        paste(text)
        return "fallback"
    time.sleep(ACTIVATE_SETTLE_SEC)
    paste(text)
    # Hand focus back to where the user is — unless that is vlow itself
    # (an alert or the Settings window), which has nothing to type into.
    if return_focus and current is not None and not is_self(current):
        activate_and_wait(current)
    return "switched"
