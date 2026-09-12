"""Check GitHub Releases for a newer vlow and install it in place.

Two install paths, picked by how vlow is running:

* Release bundle (scripts/build-release.sh): download the DMG, mount it,
  swap the .app directory next to the running one, relaunch. The app is
  ad-hoc signed, so macOS treats the new build as a new app: Accessibility
  has to be granted again after an update (a Developer ID signature would
  avoid that).
* Source checkout (``uv run vlow`` or the thin launchd bundle from
  scripts/build-app-bundle.sh): ``git pull --ff-only``, ``uv sync``,
  rebuild the thin bundle and restart through launchd (or re-exec).

Progress callbacks receive ``(fraction, text)``; ``fraction`` is None for
steps without a measurable length (git, uv, the bundle build).
"""

import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable

from .resources import bundle_contents, repo_root

REPO = "mcurses/vlow"
RELEASES_URL = f"https://github.com/{REPO}/releases"
_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
_ASSET_SUFFIX = "-arm64.dmg"
_UA = "vlow-updater"


class UpdateError(RuntimeError):
    pass


def app_path() -> Path | None:
    """The running vlow.app if this is the self-contained release bundle."""
    contents = bundle_contents()
    if contents is None or not (contents / "Resources" / "python").is_dir():
        return None
    return contents.parent


def can_self_update() -> bool:
    """True for the self-contained release bundle (DMG swap)."""
    return app_path() is not None


def source_checkout() -> Path | None:
    """The git checkout to pull when running from source, else None."""
    if can_self_update():
        return None
    return repo_root()


def can_update() -> bool:
    return can_self_update() or source_checkout() is not None


def install_kind() -> str:
    """"bundle" | "source" | "none" — which install() path applies."""
    if can_self_update():
        return "bundle"
    if source_checkout() is not None:
        return "source"
    return "none"


def current_version() -> str:
    contents = bundle_contents()
    if contents is not None:
        try:
            with open(contents / "Info.plist", "rb") as f:
                return str(plistlib.load(f).get("CFBundleShortVersionString", "0"))
        except Exception:
            pass
    try:
        from importlib.metadata import version

        return version("vlow")
    except Exception:
        return "0"


def _version_key(v: str) -> tuple:
    """'1.2.3' → (1, 2, 3); a trailing pre-release tag sorts below the plain
    version ('0.2.0-dev5' < '0.2.0'). Only used for ordering."""
    v = v.strip().lstrip("v")
    core, _, pre = v.partition("-")
    nums = tuple(int(x) if x.isdigit() else 0 for x in core.split("."))
    return nums + ((0,) if pre else (1,))


def is_newer(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def check(timeout: float = 10.0) -> dict:
    """Latest release info: {"latest", "url", "notes_url", "is_newer",
    "current"}. Raises UpdateError when there is no release or no network."""
    req = urllib.request.Request(
        _API_LATEST, headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            release = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No releases published yet.") from e
        raise UpdateError(f"GitHub returned HTTP {e.code}.") from e
    except Exception as e:
        raise UpdateError(f"Could not reach GitHub: {e}") from e
    latest = str(release.get("tag_name", "")).lstrip("v")
    asset = next(
        (a for a in release.get("assets", []) if a.get("name", "").endswith(_ASSET_SUFFIX)),
        None,
    )
    if not latest or asset is None:
        raise UpdateError("The latest release has no DMG for Apple Silicon.")
    current = current_version()
    return {
        "latest": latest,
        "current": current,
        "url": asset["browser_download_url"],
        "size": int(asset.get("size") or 0),
        "notes_url": release.get("html_url", RELEASES_URL),
        "is_newer": is_newer(latest, current),
    }


Progress = Callable[[float | None, str], None]


def install_update(info: dict, on_progress: Progress = lambda frac, text: None, relaunch: bool = True) -> None:
    """Install whichever way fits this copy of vlow (see module docstring)."""
    kind = install_kind()
    if kind == "bundle":
        install(info["url"], on_progress=on_progress, relaunch=relaunch)
    elif kind == "source":
        install_source(on_progress=on_progress, relaunch=relaunch)
    else:
        raise UpdateError("This copy of vlow cannot update itself.")


def install(
    url: str,
    on_progress: Progress = lambda frac, text: None,
    target: Path | None = None,
    relaunch: bool = True,
) -> Path:
    """Download the DMG at `url`, swap it in for `target` (default: the running
    bundle) and relaunch. Returns the installed path. Blocking — run on a
    worker thread."""
    target = target or app_path()
    if target is None:
        raise UpdateError("Only the downloaded vlow.app can update itself.")
    if not os.access(target.parent, os.W_OK):
        raise UpdateError(f"{target.parent} is not writable — move vlow.app to Applications.")

    work = Path(tempfile.mkdtemp(prefix="vlow-update-"))
    dmg = work / "vlow.dmg"
    mount = work / "mnt"
    mounted = False
    try:
        _download(url, dmg, on_progress)
        on_progress(1.0, "Installing…")
        _run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(dmg)])
        mounted = True
        source = next(mount.glob("*.app"), None)
        if source is None:
            raise UpdateError("The DMG does not contain an app.")
        staged = target.parent / (target.name + ".update")
        shutil.rmtree(staged, ignore_errors=True)
        _run(["ditto", str(source), str(staged)])  # preserves signatures/xattrs
        # Swap: keep the old bundle until the new one is in place, then drop it.
        old = target.parent / (target.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        os.rename(target, old)
        try:
            os.rename(staged, target)
        except Exception:
            os.rename(old, target)  # roll back
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        if mounted:
            subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False)
        shutil.rmtree(work, ignore_errors=True)

    if relaunch:
        _relaunch(target)
    return target


def _download(url: str, dest: Path, on_progress: Progress) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            last = 0.0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if now - last >= 0.2:
                    last = now
                    frac = done / total if total else 0.0
                    on_progress(frac, f"Downloading… {done / 1e6:.0f} of {total / 1e6:.0f} MB")
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"Download failed: {e}") from e


def install_source(
    repo: Path | None = None,
    on_progress: Progress = lambda frac, text: None,
    relaunch: bool = True,
    uv: str | None = None,
) -> Path:
    """Update a source checkout: fast-forward pull, ``uv sync``, rebuild the
    thin launchd bundle if one is in use, then restart. Blocking — run on a
    worker thread. Returns the repo path."""
    repo = repo or source_checkout()
    if repo is None:
        raise UpdateError("Not running from a source checkout.")
    git = ["git", "-C", str(repo)]

    on_progress(None, "Checking the working tree…")
    dirty = _run(git + ["status", "--porcelain", "--untracked-files=no"]).strip()
    if dirty:
        raise UpdateError(
            f"{repo} has uncommitted changes — commit or stash them, then update again."
        )
    branch = _run(git + ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if branch == "HEAD":
        raise UpdateError(f"{repo} is on a detached HEAD — check out a branch first.")

    on_progress(None, f"Pulling {branch}…")
    before = _run(git + ["rev-parse", "HEAD"]).strip()
    _run(git + ["pull", "--ff-only", "--quiet"], env=_git_env())
    after = _run(git + ["rev-parse", "HEAD"]).strip()

    uv = uv or _find_uv()
    on_progress(None, "Syncing dependencies (uv sync)…")
    _run([uv, "sync", "--frozen"], cwd=repo, env=_git_env())

    thin_bundle = repo / "dist" / "vlow.app"
    if thin_bundle.is_dir():
        on_progress(None, "Rebuilding the app bundle…")
        _run([str(repo / "scripts" / "build-app-bundle.sh")], cwd=repo, env=_git_env())

    on_progress(1.0, "Restarting…" if before != after else "Restarting (already at the latest commit)…")
    if relaunch:
        _relaunch_source(repo, thin_bundle if thin_bundle.is_dir() else None)
    return repo


def _find_uv() -> str:
    for candidate in (
        shutil.which("uv"),
        Path.home() / ".local" / "bin" / "uv",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise UpdateError("uv not found — install it from https://docs.astral.sh/uv/")


def _git_env() -> dict:
    """launchd gives us a minimal PATH; make sure git/ssh/uv helpers resolve
    and nothing waits on a terminal prompt."""
    env = dict(os.environ)
    extra = ["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin"), "/usr/bin", "/bin"]
    env["PATH"] = ":".join(extra + [p for p in env.get("PATH", "").split(":") if p and p not in extra])
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        name = Path(cmd[0]).name
        raise UpdateError(f"{name} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def _launchd_service() -> str | None:
    """'gui/<uid>/com.vlow' when the LaunchAgent is loaded, else None."""
    service = f"gui/{os.getuid()}/com.vlow"
    proc = subprocess.run(["launchctl", "print", service], capture_output=True, text=True)
    return service if proc.returncode == 0 else None


def _relaunch_source(repo: Path, thin_bundle: Path | None) -> None:
    """Restart the source install: via launchd when the agent is loaded
    (same executable path, so Accessibility survives), otherwise re-exec
    the current command line once this process has exited."""
    service = _launchd_service()
    if service is not None:
        # kickstart -k kills us and starts the new build; run it detached so
        # the kill doesn't take the launcher shell down with it.
        subprocess.Popen(
            ["launchctl", "kickstart", "-k", service],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    if thin_bundle is not None:
        _relaunch(thin_bundle)
        return
    cmd = " ".join(shlex.quote(a) for a in [sys.executable, *sys.argv])
    subprocess.Popen(
        ["/bin/sh", "-c", f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.2; done; cd {shlex.quote(str(repo))} && {cmd}"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    from AppKit import NSApplication

    NSApplication.sharedApplication().terminate_(None)


def _relaunch(target: Path) -> None:
    """Start the new bundle once this process has exited, then quit."""
    subprocess.Popen(
        ["/bin/sh", "-c", f'while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.2; done; open "{target}"'],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    from AppKit import NSApplication

    NSApplication.sharedApplication().terminate_(None)
