import subprocess
import time

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

KEYCODE_V = 9


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


def paste(text: str) -> None:
    set_clipboard(text)
    time.sleep(0.05)
    synth_cmd_v()
