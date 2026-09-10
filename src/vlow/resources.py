"""Locate bundled files (icons, the glass dylib) in both layouts vlow runs in.

Dev checkout: files live in the repo (``assets/``, ``dist/``), three levels
above this module. Release bundle (``scripts/build-release.sh``): the
package sits in ``vlow.app/Contents/Resources/python/.../site-packages`` and
the files are copied into ``Contents/Resources`` / ``Contents/Frameworks``.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def bundle_contents() -> Path | None:
    """Return ``vlow.app/Contents`` when running from a release bundle."""
    exe = Path(sys.executable).resolve()
    if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
        return exe.parent.parent
    return None


def menubar_icon_dir() -> Path:
    contents = bundle_contents()
    if contents is not None:
        return contents / "Resources" / "menubar"
    return _REPO_ROOT / "assets" / "menubar"


def glass_dylib() -> Path:
    contents = bundle_contents()
    if contents is not None:
        return contents / "Frameworks" / "libVlowGlass.dylib"
    return _REPO_ROOT / "dist" / "libVlowGlass.dylib"


def dotenv_candidates() -> list[Path]:
    """``.env`` locations, first match wins per key: repo root (dev), then
    ``~/.config/vlow/.env`` (the only option for the release bundle)."""
    return [_REPO_ROOT / ".env", Path.home() / ".config" / "vlow" / ".env"]
