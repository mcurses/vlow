import threading
from enum import Enum

import rumps
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)
from Foundation import NSOperationQueue

from .audio import Recorder
from .hotkey import DoubleTapDetector
from .overlay import Overlay
from .paste import paste
from .replay import ReplayHotkey
from .transcribe import transcribe, warmup


def request_accessibility() -> bool:
    """Trigger the macOS Accessibility prompt if not yet granted. Returns
    True if the process is currently trusted, False otherwise."""
    options = {kAXTrustedCheckOptionPrompt: True}
    return bool(AXIsProcessTrustedWithOptions(options))


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


def on_main_thread(fn):
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


class VlowApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("vlow", title="🎙", quit_button="Quit")
        self._state = State.IDLE
        self._recorder = Recorder()
        self._overlay: Overlay | None = None
        self._last_text = ""
        self._hotkey = DoubleTapDetector(self._on_double_tap)
        self._replay = ReplayHotkey(lambda: self._last_text)
        self._ready = False

        # Menubar fallbacks — reliable escape hatches if the hotkey misfires.
        self._stop_item = rumps.MenuItem("⏹ Stop & Transcribe", callback=self._menu_stop)
        self._discard_item = rumps.MenuItem("✕ Discard Recording", callback=self._menu_discard)
        self._replay_item = rumps.MenuItem("↻ Re-paste Last", callback=self._menu_replay)
        self.menu = [self._stop_item, self._discard_item, self._replay_item, None]

        self._setup_timer = rumps.Timer(self._deferred_setup, 0.3)
        self._setup_timer.start()

    def _menu_stop(self, _) -> None:
        if self._state == State.RECORDING:
            self._stop_and_transcribe()

    def _menu_discard(self, _) -> None:
        if self._state == State.RECORDING:
            self._recorder.stop()
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
        try:
            warmup()
            self._ready = True
            on_main_thread(lambda: self._set_title("🎙"))
            rumps.notification(
                "vlow ready",
                "",
                "Double-tap Right Option to start dictation.",
            )
        except Exception as e:
            print(f"warmup failed: {e}")
            on_main_thread(lambda: self._set_title("⚠️"))

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
        # ignore taps while transcribing

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
