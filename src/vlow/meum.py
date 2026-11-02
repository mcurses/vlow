"""Paste into the meum terminal tab a dictation started in.

meum (a terminal workspace app, bundle id io.github.mcurses.meum) keeps many
terminal tabs in one window, so remembering "the app that was in front" is not
enough: by the time the text is ready the user may be in another workspace.
When a recording starts in meum, vlow asks meum's control socket which tab
has focus and keeps its id; when the text is ready, it asks meum to paste
into that tab. meum inserts it as a real (bracketed) paste without changing
focus or touching the clipboard.

The socket speaks newline-delimited JSON-RPC:
  request : {"id": 1, "method": "workspace.list", "params": {}}
  response: {"id": 1, "result": ...} or {"id": 1, "error": {"code": "not_found", ...}}
It is mode 0600, so only this user's processes can connect.
"""

import json
import os
import socket
from pathlib import Path

BUNDLE_ID = "io.github.mcurses.meum"

# Asked on the main thread when a recording starts, so it has to be quick;
# a local socket answers in a few milliseconds.
FOCUS_TIMEOUT_SEC = 0.5
PASTE_TIMEOUT_SEC = 3.0


class MeumError(Exception):
    """meum answered with an error, or could not be reached (code "offline")."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def socket_path() -> Path:
    env = os.environ.get("MEUM_SOCKET")
    return Path(env) if env else Path.home() / ".local" / "state" / "meum" / "meum.sock"


def _call(method: str, params: dict, timeout: float):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(socket_path()))
            s.sendall(json.dumps({"id": 1, "method": method, "params": params}).encode() + b"\n")
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except OSError as e:
        raise MeumError("offline", str(e)) from e
    try:
        reply = json.loads(buf)
    except ValueError as e:
        raise MeumError("bad_reply", buf[:200].decode(errors="replace")) from e
    if reply.get("error"):
        err = reply["error"]
        raise MeumError(str(err.get("code", "error")), str(err.get("message", "")))
    return reply.get("result")


def is_meum(app) -> bool:
    """True if `app` (an NSRunningApplication) is meum."""
    try:
        return app is not None and str(app.bundleIdentifier() or "") == BUNDLE_ID
    except Exception:
        return False


def focused_tab() -> str | None:
    """Id of the tab that has focus in meum, or None if meum can't say."""
    try:
        result = _call("tab.focused", {}, FOCUS_TIMEOUT_SEC)
        tab = (result or {}).get("tab")
        return str(tab) if tab else None
    except MeumError as e:
        if e.code != "method_not_found":
            return None
    # Older meum: the selected workspace's focused tab says the same thing.
    try:
        for ws in _call("workspace.list", {}, FOCUS_TIMEOUT_SEC) or []:
            if ws.get("selected") and ws.get("focusedTabID"):
                return str(ws["focusedTabID"])
    except (MeumError, AttributeError, TypeError):
        pass
    return None


def paste(tab: str, text: str) -> None:
    """Paste `text` into `tab`. Raises MeumError if meum can't (tab closed:
    "not_found"; no terminal for it: "unavailable"; meum not running:
    "offline"; a meum without this method: "method_not_found")."""
    _call("tab.paste", {"tab": tab, "text": text}, PASTE_TIMEOUT_SEC)
