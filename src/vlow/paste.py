import subprocess
import time

from AppKit import NSPasteboard, NSPasteboardItem
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
