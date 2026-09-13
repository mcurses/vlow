"""Start vlow at login — the "Start at login" toggle in Settings.

Implemented as a per-user LaunchAgent rather than a Login Item, because
launchd also gives us the two things vlow already relies on: it restarts the
app if it crashes (but not when you pick Quit), and it captures stdout/stderr
into ~/Library/Logs/vlow, which is what the troubleshooting steps read.

Turning the toggle on writes the plist; turning it off deletes it. Neither
touches the running process — bootstrapping the agent while vlow is already
running would just put a second menubar icon on screen, so the change takes
effect at the next login. `scripts/vlow start` loads it immediately if you
want it now.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .resources import bundle_contents, repo_root

LABEL = "com.vlow"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "vlow"


def program_arguments() -> list[str]:
    """The command launchd should run, derived from how vlow runs right now.

    An .app bundle is strongly preferred over a bare interpreter: TCC names
    permissions after the running executable, so the bundle shows up as
    "vlow" in Privacy & Security while a venv python shows up as
    "python3.12" — and the Accessibility grant is per-executable.
    """
    contents = bundle_contents()
    if contents is None:
        # Launched as `python -m vlow` from a checkout: use the thin bundle
        # from scripts/build-app-bundle.sh if someone has built it.
        root = repo_root()
        if root is not None and (root / "dist/vlow.app/Contents/MacOS/vlow").exists():
            contents = root / "dist/vlow.app/Contents"
    if contents is None:
        return [sys.executable, "-m", "vlow"]
    exe = str(contents / "MacOS" / "vlow")
    # The self-contained release launcher runs `-m vlow` on its own; the thin
    # launchd bundle is a copy of the venv interpreter and needs the arguments.
    if (contents / "Resources" / "python").exists():
        return [exe]
    return [exe, "-m", "vlow"]


def _plist() -> dict:
    job: dict = {
        "Label": LABEL,
        "ProgramArguments": program_arguments(),
        "RunAtLoad": True,
        # Restart after a crash, but respect an explicit Quit from the menu.
        "KeepAlive": {"Crashed": True, "SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(LOG_DIR / "vlow.log"),
        "StandardErrorPath": str(LOG_DIR / "vlow.err"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            # Weights are already in ~/.cache/huggingface, and under launchd
            # huggingface_hub's "is there a newer revision?" call can hang
            # indefinitely. local_models.py lifts this for real downloads.
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
    }
    root = repo_root()
    if root is not None:
        job["WorkingDirectory"] = str(root)
    return job


def enabled() -> bool:
    return PLIST_PATH.exists()


def set_enabled(on: bool) -> None:
    """Write or remove the LaunchAgent. Takes effect at the next login."""
    if on:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PLIST_PATH.with_suffix(".plist.tmp")
        with open(tmp, "wb") as f:
            plistlib.dump(_plist(), f)
        os.replace(tmp, PLIST_PATH)
        # Clear a disabled flag from an earlier `launchctl disable`, which
        # would otherwise keep the agent from loading at login.
        _launchctl("enable", f"gui/{os.getuid()}/{LABEL}")
    else:
        PLIST_PATH.unlink(missing_ok=True)


def refresh() -> None:
    """Rewrite the plist if it is enabled but points somewhere stale — e.g.
    after moving from a source checkout to /Applications/vlow.app, where the
    recorded executable no longer exists or is no longer the one running."""
    if not enabled():
        return
    try:
        with open(PLIST_PATH, "rb") as f:
            current = plistlib.load(f).get("ProgramArguments")
    except Exception:
        current = None
    if current != program_arguments():
        set_enabled(True)


def _launchctl(*args: str) -> None:
    try:
        subprocess.run(
            ["launchctl", *args], check=False, capture_output=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[vlow] launchctl {' '.join(args)} failed: {e}", flush=True)
