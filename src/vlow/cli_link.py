"""`vlow` on your PATH — a symlink in ~/.local/bin pointing at this install.

That directory belongs to the user, so the link is created on first launch
without an admin prompt and without touching anything outside $HOME. What we
do *not* do is edit a shell rc file: if ~/.local/bin is not on PATH we show
the one line to add and leave the decision to the user (the uv / pipx
pattern).

The link is written by path, not by inode, so it survives an update: the
DMG swap in updater.install() puts the new bundle back at the same place.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from .resources import bundle_contents, repo_root

BIN_DIR = Path.home() / ".local" / "bin"
LINK_PATH = BIN_DIR / "vlow"
PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'

# `scripts/vlow` (a launchd helper that shadowed the real CLI) used to install
# itself under these names. It no longer exists, so those links now dangle.
LEGACY_LINKS = (Path("/opt/homebrew/bin/vlow"), Path("/usr/local/bin/vlow"))


def _log(msg: str) -> None:
    print(f"[vlow {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def target() -> Path | None:
    """The executable that a `vlow` on PATH should point at, or None if this
    copy has nothing linkable.

    Release bundle: Contents/MacOS/vlow, which embeds the interpreter and
    forwards its arguments to `-m vlow` (native/launcher.c), so it is the
    complete CLI. The thin launchd bundle from scripts/build-app-bundle.sh
    has the same layout but is a bare copy of the venv interpreter — running
    it without `-m vlow` drops you in a REPL — so a checkout links the
    console script instead.
    """
    contents = bundle_contents()
    if contents is not None and (contents / "Resources" / "python").is_dir():
        return contents / "MacOS" / "vlow"
    root = repo_root()
    if root is not None:
        script = root / ".venv" / "bin" / "vlow"
        if script.exists():
            return script
    return None


def _is_ours(link: Path) -> bool:
    """True when `link` is a symlink this code may repoint.

    Ownership is judged by where it points, not by where it is: a symlink
    named vlow aiming at a bundle executable, a venv console script or the
    retired scripts/vlow is one of ours. A regular file, or a symlink to
    anything else, belongs to somebody else and is left alone.
    """
    if not link.is_symlink():
        return False
    dest = Path(os.readlink(link))
    return dest.name == "vlow" and dest.parent.name in ("MacOS", "bin", "scripts")


def _link_state(exe: Path | None) -> str:
    """ok | missing | stale | foreign | unavailable"""
    if exe is None:
        return "unavailable"
    if not LINK_PATH.exists() and not LINK_PATH.is_symlink():
        return "missing"
    if not _is_ours(LINK_PATH):
        return "foreign"
    return "ok" if Path(os.readlink(LINK_PATH)) == exe else "stale"


_shell_path: str | None = None


def shell_path(timeout: float = 5.0, refresh: bool = False) -> str:
    """The PATH of the user's *login shell*.

    os.environ is the wrong place to look: under launchd vlow inherits the
    short PATH hardcoded in login_item._plist(), which has no ~/.local/bin in
    it no matter what the user's shell does. Ask the shell itself, with -i so
    that ~/.zshrc (where people actually put their exports) is sourced, and
    fence the answer with a marker so rc-file chatter cannot be mistaken for
    it.
    """
    global _shell_path
    if _shell_path is not None and not refresh:
        return _shell_path
    shell = os.environ.get("SHELL") or "/bin/zsh"
    marker = "__vlow_path__:"
    try:
        proc = subprocess.run(
            [shell, "-lic", f'printf "\\n{marker}%s\\n" "$PATH"'],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log(f"could not read the login shell PATH ({e}); using this process's")
        _shell_path = os.environ.get("PATH", "")
        return _shell_path
    for line in proc.stdout.splitlines():
        if line.startswith(marker):
            _shell_path = line[len(marker):]
            return _shell_path
    _shell_path = os.environ.get("PATH", "")
    return _shell_path


def on_path(path_value: str | None = None) -> bool:
    value = shell_path() if path_value is None else path_value
    return str(BIN_DIR) in [p.rstrip("/") for p in value.split(":") if p]


def status(check_path: bool = True) -> dict:
    """Everything the Settings window and `vlow status` want to show."""
    exe = target()
    state = _link_state(exe)
    return {
        "state": state,
        "link": str(LINK_PATH),
        "target": str(exe) if exe else "",
        # Only meaningful once the link exists; skip the subshell otherwise.
        "on_path": on_path() if (check_path and state in ("ok", "stale")) else False,
        "path_line": PATH_LINE,
    }


def install(force: bool = False) -> dict:
    """Create or repoint the symlink. Returns status().

    Idempotent and silent by design — it writes inside the user's own
    ~/.local/bin, so there is nothing to ask about. `force` is for the
    Settings button: it replaces even a file we did not put there.
    """
    exe = target()
    if exe is None:
        return status()
    state = _link_state(exe)
    if state == "ok":
        return status()
    if state == "foreign" and not force:
        _log(f"{LINK_PATH} exists and is not ours — leaving it alone")
        return status()

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    # Swap through a temporary name: os.symlink cannot overwrite, and an
    # unlink+symlink pair would leave `vlow` missing if we died in between.
    tmp = LINK_PATH.with_name(f".vlow.link.{os.getpid()}")
    tmp.unlink(missing_ok=True)
    os.symlink(exe, tmp)
    os.replace(tmp, LINK_PATH)
    _log(f"linked {LINK_PATH} → {exe}")
    return status()


def uninstall() -> None:
    """Remove the link, but only if it is still ours."""
    if _is_ours(LINK_PATH):
        LINK_PATH.unlink(missing_ok=True)
        _log(f"removed {LINK_PATH}")


def migrate_legacy() -> None:
    """Repair the links the retired scripts/vlow left behind.

    It installed itself as /opt/homebrew/bin/vlow, which a `git pull` onto
    this version turns into a dangling symlink — `vlow` in a terminal would
    fail outright instead of merely running the wrong program. Repoint it at
    the real CLI where the directory is writable, drop it where it is not.
    """
    exe = target()
    for link in LEGACY_LINKS:
        if not link.is_symlink():
            continue
        dest = Path(os.readlink(link))
        if dest.parent.name != "scripts":  # not the old helper — hands off
            continue
        if exe is not None and os.access(link.parent, os.W_OK):
            tmp = link.with_name(f".vlow.link.{os.getpid()}")
            tmp.unlink(missing_ok=True)
            os.symlink(exe, tmp)
            os.replace(tmp, link)
            _log(f"migrated {link} → {exe}")
        else:
            try:
                link.unlink()
                _log(f"removed the stale {link}")
            except OSError as e:
                _log(f"{link} is stale and could not be removed ({e}); delete it by hand")


def ensure() -> None:
    """Startup hook: fix old links, then make sure ours is in place."""
    migrate_legacy()
    st = install()
    if st["state"] in ("ok", "stale") and not st["on_path"]:
        _log(f"{BIN_DIR} is not on your PATH — add it with: {PATH_LINE}")
