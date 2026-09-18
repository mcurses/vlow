"""The `vlow` command: menubar app by default, plus two one-shot subcommands.

    vlow                    run the menubar app (what the .app bundle does)
    vlow test [SECONDS]     record from the mic and print the transcript
    vlow transcribe FILE…   transcribe audio files and print the transcript
    vlow selftest           check this install can load everything it needs
"""

import argparse
import contextlib
import os
import sys
import time


def _log(msg: str) -> None:
    print(f"[vlow {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _override_backend(backend: str | None, model: str | None) -> None:
    """Apply --backend / --model for this process only (config.toml is not
    touched); the transcribe dispatcher reads both from the environment."""
    if backend:
        os.environ["VLOW_BACKEND"] = backend
    if model:
        os.environ["VLOW_LOCAL_MODEL"] = model


def test_record(seconds: float = 4.0) -> None:
    """Record from the default mic for N seconds, transcribe, print result."""
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


def transcribe_files(paths: list[str], out_path: str | None = None) -> int:
    """Transcribe each file with the configured backend. Transcripts go to
    stdout (or --output); progress and errors go to stderr, so the output
    stays pipeable. Returns the process exit code."""
    from .audio import SAMPLE_RATE, load_file
    from .transcribe import transcribe

    chunks: list[str] = []
    failed = 0
    for path in paths:
        try:
            audio = load_file(path)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"vlow: {e}", file=sys.stderr)
            failed += 1
            continue
        duration = audio.size / SAMPLE_RATE
        print(
            f"[vlow] {os.path.basename(path)}: {duration:.1f}s audio…",
            file=sys.stderr,
            flush=True,
        )
        try:
            # The backends log progress to stdout (that is the launchd log);
            # here stdout is the transcript, so send their chatter to stderr.
            with contextlib.redirect_stdout(sys.stderr):
                text = transcribe(audio).strip()
        except Exception as e:
            print(f"vlow: {os.path.basename(path)}: {e}", file=sys.stderr)
            failed += 1
            continue
        # Only label the files when there is more than one, so the common
        # single-file call stays a clean transcript you can pipe onward.
        chunks.append(f"# {os.path.basename(path)}\n{text}" if len(paths) > 1 else text)

    if not chunks:
        return 1
    result = "\n\n".join(chunks) + "\n"
    if out_path:
        with open(out_path, "w") as f:
            f.write(result)
        print(f"[vlow] wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(result)
    return 1 if failed else 0


def selftest(require_bundle: bool = False) -> int:
    """Import the whole app stack and check the files it needs are reachable.

    The release build runs this from inside the .app (`selftest --bundled`),
    which is why it has to go through the bundle executable rather than a
    bare interpreter: only then is sys.executable Contents/MacOS/vlow, which
    is what resources.bundle_contents() keys off.
    """
    import vlow.app  # noqa: F401
    import vlow.local_models  # noqa: F401
    import vlow.overlay  # noqa: F401
    import vlow.settings_window  # noqa: F401
    import vlow.stream_aai  # noqa: F401
    import vlow.transcribe_mlx  # noqa: F401
    import vlow.transcribe_parakeet  # noqa: F401
    import vlow.updater  # noqa: F401
    import mlx.core
    import mlx_whisper  # noqa: F401
    import numba  # noqa: F401
    import rumps  # noqa: F401
    import sounddevice  # noqa: F401

    from . import resources

    problems = []
    contents = resources.bundle_contents()
    if require_bundle and contents is None:
        problems.append(f"not running from an .app bundle: {sys.executable}")
    dylib = resources.glass_dylib()
    if not dylib.exists():
        problems.append(f"missing glass dylib: {dylib} (run scripts/build-glass.sh)")
    icon = resources.menubar_icon_dir() / "mic.png"
    if not icon.exists():
        problems.append(f"missing menubar icons: {icon}")

    where = "bundle" if contents is not None else "checkout"
    print(
        f"   python {sys.version.split()[0]} | mlx {mlx.core.__version__} "
        f"| {where} | {'ok' if not problems else 'FAILED'}"
    )
    for p in problems:
        print(f"   ✗ {p}", file=sys.stderr)
    return 1 if problems else 0


def run_app() -> None:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    from .app import VlowApp

    # The .app bundle sets LSUIElement, but Contents/MacOS/vlow execs into the
    # venv interpreter — so the running executable is Homebrew's Python.app and
    # macOS reads *its* Info.plist, which has no LSUIElement. Result: a Dock
    # rocket for a menu-bar-only daemon. Set the policy at runtime instead,
    # where bundle identity doesn't matter. Must happen before the runloop.
    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory
    )
    app = VlowApp()
    _log("entering runloop")
    app.run()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vlow",
        description="Local voice dictation for macOS. Without a subcommand, "
        "vlow runs as a menubar app.",
    )
    sub = p.add_subparsers(dest="command")

    test = sub.add_parser("test", help="record from the mic and print the transcript")
    test.add_argument(
        "seconds", nargs="?", type=float, default=4.0, help="how long to record (default 4)"
    )

    st = sub.add_parser("selftest", help="check this install can load everything")
    st.add_argument(
        "--bundled", action="store_true",
        help="also require running from inside vlow.app (used by the release build)",
    )

    tr = sub.add_parser("transcribe", help="transcribe audio files")
    tr.add_argument("files", nargs="+", metavar="FILE", help="any format ffmpeg can decode")
    tr.add_argument("-o", "--output", metavar="PATH", help="write to a file instead of stdout")
    for q in (test, tr):
        q.add_argument(
            "--backend",
            choices=("mlx", "assemblyai", "auto"),
            help="override the configured backend for this run",
        )
        q.add_argument(
            "--model",
            metavar="KEY",
            help="override the on-device model for this run "
            "(whisper-large-v3 | parakeet-tdt-0.6b-v3)",
        )
    return p


def main() -> None:
    from .config import load as load_config
    from .diag import install_power_logging, install_signal_dump

    args = _parser().parse_args()  # before any logging, so --help stays clean
    _log("starting…")
    install_signal_dump()
    install_power_logging()
    load_config()

    if args.command == "selftest":
        sys.exit(selftest(args.bundled))
    if args.command == "test":
        _override_backend(args.backend, args.model)
        test_record(args.seconds)
    elif args.command == "transcribe":
        _override_backend(args.backend, args.model)
        sys.exit(transcribe_files(args.files, args.output))
    else:
        run_app()


if __name__ == "__main__":
    main()
