import sys

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from .app import VlowApp
from .config import load as load_config


def test_record(seconds: float = 4.0) -> None:
    """Record from the default mic for N seconds, transcribe, print result."""
    import time

    from .audio import Recorder
    from .transcribe import transcribe, warmup

    print("loading model...")
    t0 = time.time()
    warmup()
    print(f"  warmup: {time.time() - t0:.1f}s")

    rec = Recorder()
    print(f"recording {seconds}s — speak now...")
    rec.start()
    time.sleep(seconds)
    audio = rec.stop()
    print(f"  captured: {audio.size / 16000:.2f}s of audio")

    t0 = time.time()
    text = transcribe(audio)
    print(f"  transcribe: {time.time() - t0:.1f}s")
    print(f"\n>> {text!r}")


def main() -> None:
    import time

    from .diag import install_power_logging, install_signal_dump

    print(f"[vlow {time.strftime('%H:%M:%S')}] starting…", file=sys.stderr, flush=True)
    install_signal_dump()
    install_power_logging()
    load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        secs = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
        test_record(secs)
        return
    # The .app bundle sets LSUIElement, but Contents/MacOS/vlow execs into the
    # venv interpreter — so the running executable is Homebrew's Python.app and
    # macOS reads *its* Info.plist, which has no LSUIElement. Result: a Dock
    # rocket for a menu-bar-only daemon. Set the policy at runtime instead,
    # where bundle identity doesn't matter. Must happen before the runloop.
    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory
    )
    app = VlowApp()
    print(
        f"[vlow {time.strftime('%H:%M:%S')}] entering runloop",
        file=sys.stderr,
        flush=True,
    )
    app.run()


if __name__ == "__main__":
    main()
