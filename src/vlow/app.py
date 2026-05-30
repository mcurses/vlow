import threading
from enum import Enum

import rumps
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)
from Foundation import NSOperationQueue

from .audio import Recorder
from .config import load as load_config
from .hotkey import DoubleTapDetector, HoldDetector, TapHoldDetector
from .overlay import Overlay
from .paste import paste
from .replay import ReplayHotkey
from .stream_aai import StreamingSession
from .transcribe import auto_threshold_sec, backend_name, transcribe, warmup


def _backend_label() -> str:
    name = backend_name()
    if name == "auto":
        return f"Backend: auto (>{auto_threshold_sec():.0f}s → assemblyai)"
    return f"Backend: {name}"


def request_accessibility() -> bool:
    """Trigger the macOS Accessibility prompt if not yet granted. Returns
    True if the process is currently trusted, False otherwise."""
    options = {kAXTrustedCheckOptionPrompt: True}
    return bool(AXIsProcessTrustedWithOptions(options))


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"      # batch mic capture (toggle gesture)
    STREAMING = "streaming"      # live AAI stream (hold gesture)
    TRANSCRIBING = "transcribing"  # batch finished, awaiting result
    FINALIZING = "finalizing"    # stream stopped, awaiting last finals


def on_main_thread(fn):
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


VALID_MODES = ("toggle", "ptt")


class VlowApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("vlow", title="🎙", quit_button="Quit")
        self._config = load_config()
        self._mode = self._config.get("mode", "toggle")
        if self._mode not in VALID_MODES:
            raise ValueError(f"config.mode must be one of {VALID_MODES}, got {self._mode!r}")
        self._state = State.IDLE
        self._recorder = Recorder()
        self._stream: StreamingSession | None = None
        self._pasted_in_session = False
        self._overlay: Overlay | None = None
        self._last_text = ""
        self._replay = ReplayHotkey(lambda: self._last_text)
        self._ready = False

        if self._mode == "ptt":
            self._hotkey = HoldDetector(
                self._start_stream,
                self._stop_stream,
                hotkey=self._config["hotkey"],
            )
        else:  # toggle — double-tap = batch, hold = streaming
            self._hotkey = TapHoldDetector(
                on_double_tap=self._on_double_tap,
                on_hold_start=self._start_stream,
                on_hold_end=self._stop_stream,
                hotkey=self._config["hotkey"],
            )

        # Menubar fallbacks — reliable escape hatches if the hotkey misfires.
        self._mode_item = rumps.MenuItem(f"Mode: {self._mode}")
        self._mode_item.set_callback(None)
        self._backend_item = rumps.MenuItem(_backend_label())
        self._backend_item.set_callback(None)
        self._stop_item = rumps.MenuItem("⏹ Stop & Transcribe", callback=self._menu_stop)
        self._discard_item = rumps.MenuItem("✕ Discard Recording", callback=self._menu_discard)
        self._replay_item = rumps.MenuItem("↻ Re-paste Last", callback=self._menu_replay)
        self.menu = [
            self._mode_item,
            self._backend_item,
            None,
            self._stop_item,
            self._discard_item,
            self._replay_item,
            None,
        ]

        self._setup_timer = rumps.Timer(self._deferred_setup, 0.3)
        self._setup_timer.start()

    def _menu_stop(self, _) -> None:
        if self._state == State.RECORDING:
            self._stop_and_transcribe()
        elif self._state == State.STREAMING:
            self._stop_stream()

    def _menu_discard(self, _) -> None:
        if self._state == State.RECORDING:
            self._recorder.stop()
            self._reset()
        elif self._state == State.STREAMING and self._stream is not None:
            try:
                self._stream.stop()
            except Exception as e:
                print(f"discard stream error: {e}", flush=True)
            self._stream = None
            self._reset()

    def _menu_replay(self, _) -> None:
        if self._last_text:
            paste(self._last_text)

    def _deferred_setup(self, sender) -> None:
        sender.stop()
        trusted = request_accessibility()
        if not trusted:
            rumps.notification(
                "vlow needs Accessibility",
                "",
                "Grant Accessibility to your terminal in System Settings, then relaunch vlow.",
            )
        self._overlay = Overlay()
        self._hotkey.start()
        self._replay.start()
        self.title = "🎙…"
        threading.Thread(target=self._warmup, daemon=True).start()

    def _warmup(self) -> None:
        import os as _os
        try:
            if self._mode == "ptt":
                if not _os.environ.get("ASSEMBLYAI_API_KEY"):
                    raise RuntimeError("ASSEMBLYAI_API_KEY required for ptt mode.")
            else:
                # toggle mode: mlx for batch; aai key needed for the hold gesture.
                warmup()
            self._ready = True
            on_main_thread(lambda: self._set_title("🎙"))
            hotkey_label = self._config["hotkey"].replace("_", " ").title()
            if self._mode == "ptt":
                rumps.notification(
                    "vlow ready",
                    "mode: ptt — live streaming",
                    f"Hold {hotkey_label} to talk.",
                )
            else:
                aai_ok = bool(_os.environ.get("ASSEMBLYAI_API_KEY"))
                hold_hint = (
                    "hold for live streaming"
                    if aai_ok
                    else "hold disabled — ASSEMBLYAI_API_KEY missing"
                )
                rumps.notification(
                    "vlow ready",
                    f"backend: {backend_name()} · {hold_hint}",
                    f"Double-tap {hotkey_label} to record, hold to stream.",
                )
        except Exception as e:
            print(f"warmup failed: {e}", flush=True)
            on_main_thread(lambda: self._set_title("⚠️"))
            rumps.notification("vlow warmup failed", self._mode, str(e))

    def _set_title(self, t: str) -> None:
        self.title = t

    def _on_double_tap(self) -> None:
        if not self._ready:
            rumps.notification("vlow", "", "Model still loading…")
            return
        if self._state == State.IDLE:
            self._start_recording()
        elif self._state == State.RECORDING:
            self._stop_and_transcribe()
        # ignore taps while transcribing or streaming

    def _start_stream(self) -> None:
        # Hold gesture can fire while the user is also in a batch session —
        # ignore unless we're idle.
        if not self._ready or self._state != State.IDLE:
            return
        self._state = State.STREAMING
        self._pasted_in_session = False
        self._last_text = ""
        self.title = "🔴"
        if self._overlay is not None:
            self._overlay.show("● Streaming…")
        self._stream = StreamingSession(
            on_partial=self._on_stream_partial,
            on_final=self._on_stream_final,
        )
        try:
            self._stream.start()
        except Exception as e:
            print(f"stream start error: {e}", flush=True)
            rumps.notification("vlow stream error", "", str(e))
            self._stream = None
            self._reset()

    def _stop_stream(self) -> None:
        if self._state != State.STREAMING or self._stream is None:
            return
        self._state = State.FINALIZING
        self.title = "⏳"
        if self._overlay is not None:
            self._overlay.update("⏳ Finalizing…")
        threading.Thread(target=self._finish_stream, daemon=True).start()

    def _finish_stream(self) -> None:
        session = self._stream
        try:
            if session is not None:
                session.stop()  # late finals fire via on_final during this
        except Exception as e:
            print(f"stream stop error: {e}", flush=True)
        finally:
            self._stream = None
        on_main_thread(self._after_stream)

    def _after_stream(self) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self.title = "🎙"
        self._state = State.IDLE

    def _on_stream_partial(self, text: str) -> None:
        if self._overlay is None:
            return
        display = text if len(text) <= 60 else "…" + text[-60:]
        on_main_thread(lambda: self._overlay.update(f"● {display}"))

    def _on_stream_final(self, text: str) -> None:
        # Paste each final turn progressively so dictation appears live in the
        # focused app. Add a leading space between turns of the same session.
        if self._pasted_in_session:
            chunk = " " + text
        else:
            chunk = text
            self._pasted_in_session = True
        try:
            paste(chunk)
        except Exception as e:
            print(f"live paste error: {e}", flush=True)
        self._last_text = (self._last_text + " " + text).strip() if self._last_text else text

    def _start_recording(self) -> None:
        self._state = State.RECORDING
        self.title = "🔴"
        if self._overlay is not None:
            self._overlay.show("● Listening…")
        try:
            self._recorder.start()
        except Exception as e:
            print(f"failed to start audio: {e}")
            self._reset()

    def _stop_and_transcribe(self) -> None:
        self._state = State.TRANSCRIBING
        self.title = "⏳"
        if self._overlay is not None:
            self._overlay.update("⏳ Transcribing…")
        audio = self._recorder.stop()
        threading.Thread(target=self._do_transcribe, args=(audio,), daemon=True).start()

    def _do_transcribe(self, audio) -> None:
        text = ""
        try:
            text = transcribe(audio)
        except Exception as e:
            print(f"transcribe error: {e}")
        on_main_thread(lambda: self._finish(text))

    def _finish(self, text: str) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self.title = "🎙"
        self._state = State.IDLE
        if text:
            self._last_text = text
            paste(text)

    def _reset(self) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self.title = "🎙"
        self._state = State.IDLE
