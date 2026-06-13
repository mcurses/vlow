import sys

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
    print(f"[vlow {time.strftime('%H:%M:%S')}] starting…", file=sys.stderr, flush=True)
    load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        secs = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
        test_record(secs)
        return
    app = VlowApp()
    print(
        f"[vlow {time.strftime('%H:%M:%S')}] entering runloop",
        file=sys.stderr,
        flush=True,
    )
    app.run()


if __name__ == "__main__":
    main()
