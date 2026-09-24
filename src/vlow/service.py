"""Control the background vlow: `vlow start|stop|restart|status|logs`.

These are capabilities of vlow, not of a checkout, so they live in the CLI
next to `transcribe` — and they read the label, the plist path and the log
directory from login_item, which is the one module that writes the agent.
A second copy of those names (this used to be a shell script) could drift
from it silently.
"""

import os
import subprocess
import sys
from pathlib import Path

from . import cli_link
from .login_item import LABEL, LOG_DIR, PLIST_PATH, enabled

ERR_LOG = LOG_DIR / "vlow.err"
OUT_LOG = LOG_DIR / "vlow.log"


def _service() -> str:
    return f"gui/{os.getuid()}/{LABEL}"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _loaded() -> bool:
    return _launchctl("print", _service()).returncode == 0


def _fail(msg: str) -> int:
    print(f"vlow: {msg}", file=sys.stderr)
    return 1


def _not_enabled() -> int:
    return _fail(
        "vlow is not set up to run in the background.\n"
        '       Turn on "Start vlow at login" in Settings, then try again.'
    )


def start() -> int:
    if not enabled():
        return _not_enabled()
    # bootstrap fails with EALREADY when it is already loaded; kickstart then
    # starts it whether it was loaded just now or long ago.
    _launchctl("bootstrap", f"gui/{os.getuid()}", str(PLIST_PATH))
    proc = _launchctl("kickstart", _service())
    if proc.returncode != 0:
        return _fail(f"could not start: {proc.stderr.strip() or proc.stdout.strip()}")
    print("vlow started.")
    return 0


def stop() -> int:
    if not _loaded():
        print("vlow is not running under launchd.")
        return 0
    proc = _launchctl("bootout", _service())
    if proc.returncode != 0:
        return _fail(f"could not stop: {proc.stderr.strip() or proc.stdout.strip()}")
    print("vlow stopped (until 'vlow start' or your next login).")
    return 0


def restart() -> int:
    if not _loaded():
        return start()
    proc = _launchctl("kickstart", "-k", _service())
    if proc.returncode != 0:
        return _fail(f"could not restart: {proc.stderr.strip() or proc.stdout.strip()}")
    print("vlow restarted.")
    return 0


def status() -> int:
    if _loaded():
        # `launchctl print` repeats "state" for every nested endpoint; the
        # job's own value is the first one, at a single level of indent.
        printed = _launchctl("print", _service()).stdout
        for key in ("state", "pid"):
            line = next(
                (l for l in printed.splitlines() if l.startswith(f"\t{key} = ")), None
            )
            if line is not None:
                print(line.strip())
    elif enabled():
        print("not running (run 'vlow start')")
    else:
        print('not running, and not set to start at login (Settings → "Start vlow at login")')

    link = cli_link.status()
    where = link["target"] or "unknown"
    if link["state"] == "ok" and not link["on_path"]:
        print(f"cli: {link['link']} → {where} (not on your PATH — add {link['path_line']})")
    elif link["state"] == "ok":
        print(f"cli: {link['link']} → {where}")
    else:
        print(f"cli: {link['state']} ({link['link']}) — run 'vlow install-cli'")

    print(f"--- last log lines ({ERR_LOG}):")
    try:
        lines = ERR_LOG.read_text(errors="replace").splitlines()[-5:]
        print("\n".join(lines) if lines else "(empty)")
    except OSError:
        print("(no log yet)")
    return 0


def logs(lines: int = 20) -> int:
    """Live tail of the error log — the one launchd writes vlow's stderr to."""
    if not ERR_LOG.exists():
        return _fail(f"no log at {ERR_LOG} — vlow logs there only when launchd starts it.")
    try:
        os.execvp("tail", ["tail", "-n", str(lines), "-F", str(ERR_LOG)])
    except OSError as e:
        return _fail(f"could not tail {ERR_LOG}: {e}")
    return 0  # unreachable: execvp replaces the process


def install_cli(force: bool = False) -> int:
    """`vlow install-cli` — put (or repair) `vlow` on the user's PATH."""
    cli_link.migrate_legacy()
    st = cli_link.install(force=force)
    if st["state"] == "unavailable":
        return _fail(
            "this copy of vlow has no linkable executable "
            "(run it from vlow.app or from a checkout with a .venv)."
        )
    if st["state"] == "foreign":
        return _fail(
            f"{st['link']} already exists and was not created by vlow.\n"
            "       Remove it, or re-run with --force to replace it."
        )
    print(f"{st['link']} → {st['target']}")
    if not st["on_path"]:
        print()
        print(f"{Path(st['link']).parent} is not on your PATH. Add it with:")
        print(f"    echo '{st['path_line']}' >> ~/.zshrc")
    return 0
