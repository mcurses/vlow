import sys
import threading
import time
from enum import Enum
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[vlow {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

import rumps
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)
from Foundation import NSOperationQueue

from .audio import Recorder, default_input_name, list_input_devices, refresh_devices
from .config import load as load_config
from .diag import Watchdog
from .hotkey import EVENT_STATS, DoubleTapDetector, HoldDetector, TapHoldDetector
from .overlay import Overlay
from .paste import (
    POST_PASTE_WAIT_SEC,
    paste,
    paste_no_restore,
    restore_clipboard,
    snapshot_clipboard,
)
from .recordings import LATEST_PATH as RECORDING_PATH, reveal_in_finder, save_float32
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

# Menubar status icons (SF Symbol renders, see scripts/gen-menubar-icons.py).
# key → (filename, is_template). Template icons adapt to menubar appearance;
# the recording icon stays system-red.
_ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "menubar"
_STATUS_ICONS = {
    "loading": ("mic-dim.png", True),
    "idle": ("mic.png", True),
    "recording": ("mic-red.png", False),
    "busy": ("waveform.png", True),
    "error": ("warn.png", True),
}


class VlowApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("vlow", quit_button="Quit")
        self._status_key = ""
        self._set_status_icon("loading")
        self._config = load_config()
        self._mode = self._config.get("mode", "toggle")
        if self._mode not in VALID_MODES:
            raise ValueError(f"config.mode must be one of {VALID_MODES}, got {self._mode!r}")
        self._state = State.IDLE
        self._input_device: int | None = None  # None → follow system default
        self._recorder = Recorder()
        self._stream: StreamingSession | None = None
        self._pasted_in_session = False
        self._preserved_clipboard: list[dict[str, bytes]] | None = None
        self._overlay: Overlay | None = None
        self._last_level_ts = 0.0  # throttles meter updates onto the main thread
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
        self._stop_item = rumps.MenuItem("Stop & Transcribe", callback=self._menu_stop)
        self._discard_item = rumps.MenuItem("Discard Recording", callback=self._menu_discard)
        self._replay_item = rumps.MenuItem("Re-paste Last", callback=self._menu_replay)
        self._reveal_item = rumps.MenuItem("Reveal Last Recording", callback=self._menu_reveal)
        self._device_menu = rumps.MenuItem("Input Device")
        self._populate_device_menu()
        self.menu = [
            self._mode_item,
            self._backend_item,
            self._device_menu,
            None,
            self._stop_item,
            self._discard_item,
            self._replay_item,
            self._reveal_item,
            None,
        ]

        # NSEvent monitor + NSPanel + threads don't actually need NSApp.run()
        # to be active; both rumps.Timer and NSOperationQueue main-queue
        # one-shots were never firing on macOS 26, so run setup inline.
        self._deferred_setup(None)

    def _populate_device_menu(self) -> None:
        try:
            self._device_menu.clear()
        except Exception:
            pass
        # Item 0: follow system default. Selection shows as a native checkmark.
        default_item = rumps.MenuItem(
            "Use System Default", callback=self._select_default_device
        )
        default_item.state = 1 if self._input_device is None else 0
        self._device_menu.add(default_item)
        # One item per discovered input device.
        for d in list_input_devices():
            tag_str = "  (system default)" if d["is_default"] else ""
            item = rumps.MenuItem(
                f"{d['name']}{tag_str}", callback=self._make_device_selector(d["index"])
            )
            item.state = 1 if self._input_device == d["index"] else 0
            self._device_menu.add(item)
        self._device_menu.add(None)  # separator
        self._device_menu.add(
            rumps.MenuItem("Refresh Devices", callback=self._menu_refresh_devices)
        )

    def _make_device_selector(self, idx: int):
        def cb(_sender):
            self._input_device = idx
            self._populate_device_menu()
            rumps.notification("vlow", "input device", f"Pinned to device #{idx}")
        return cb

    def _select_default_device(self, _) -> None:
        self._input_device = None
        self._populate_device_menu()
        rumps.notification(
            "vlow",
            "input device",
            f"Following system default ({default_input_name()})",
        )

    def _menu_refresh_devices(self, _) -> None:
        refresh_devices()
        self._populate_device_menu()
        rumps.notification("vlow", "input devices", "Refreshed device list")

    def _menu_stop(self, _) -> None:
        _log(f"menu: stop & transcribe (state={self._state.value})")
        if self._state == State.RECORDING:
            self._stop_and_transcribe()
        elif self._state == State.STREAMING:
            self._stop_stream()

    def _menu_discard(self, _) -> None:
        _log(f"menu: discard (state={self._state.value})")
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

    def _menu_reveal(self, _) -> None:
        if not reveal_in_finder():
            rumps.notification(
                "vlow",
                "no recording yet",
                f"{RECORDING_PATH} doesn't exist — record something first.",
            )

    def _deferred_setup(self, _sender) -> None:
        _log(f"deferred setup: mode={self._mode} hotkey={self._config['hotkey']}")
        try:
            trusted = request_accessibility()
        except Exception as e:
            _log(f"accessibility check failed: {e}")
            trusted = False
        _log(f"accessibility trusted={trusted}")
        if not trusted:
            rumps.notification(
                "vlow needs Accessibility",
                "",
                "Grant Accessibility in System Settings → Privacy & Security, then relaunch vlow.",
            )
        try:
            self._overlay = Overlay()
            _log("overlay built")
        except Exception as e:
            _log(f"overlay build failed: {e}")
        try:
            self._hotkey.start()
            _log(f"hotkey monitor started ({type(self._hotkey).__name__})")
        except Exception as e:
            _log(f"hotkey start failed: {e}")
        try:
            self._replay.start()
            _log("replay hotkey started")
        except Exception as e:
            _log(f"replay start failed: {e}")
        self._set_status_icon("loading")
        threading.Thread(target=self._warmup, daemon=True).start()
        _log("warmup thread spawned")
        self._watchdog = Watchdog(
            on_main=on_main_thread,
            probe_main=self._probe_main,
            get_state=lambda: self._state.value,
            is_idle=lambda: self._state is State.IDLE,
        )
        self._watchdog.start()
        _log("watchdog started (ping 60s, heartbeat ~5min, `kill -USR1` dumps stacks)")

    def _probe_main(self) -> str:
        """Runs on the main thread via the watchdog ping; summarizes UI health."""
        bits = [f"icon={self._status_key}", EVENT_STATS.summary()]
        try:
            item = self._nsapp.nsstatusitem
            button = item.button()
            window = button.window() if button is not None else None
            win_no = int(window.windowNumber()) if window is not None else None
            bits.append(f"statusitem: win={win_no} visible={bool(item.isVisible())}")
        except Exception as e:
            bits.append(f"statusitem: probe failed ({e})")
        return " ".join(bits)

    def _to_state(self, new: "State", why: str) -> None:
        _log(f"state: {self._state.value} → {new.value} ({why})")
        self._state = new

    def _warmup(self) -> None:
        import os as _os
        try:
            _log(f"warmup start (mode={self._mode}, backend={backend_name()})")
            t0 = time.time()
            if self._mode == "ptt":
                if not _os.environ.get("ASSEMBLYAI_API_KEY"):
                    raise RuntimeError("ASSEMBLYAI_API_KEY required for ptt mode.")
            else:
                # toggle mode: mlx for batch; aai key needed for the hold gesture.
                warmup()
            _log(f"warmup done in {time.time()-t0:.1f}s — hotkey is live")
            self._ready = True
            on_main_thread(lambda: self._set_status_icon("idle"))
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
            on_main_thread(lambda: self._set_status_icon("error"))
            rumps.notification("vlow warmup failed", self._mode, str(e))

    def _set_status_icon(self, key: str) -> None:
        if key == self._status_key:
            return
        self._status_key = key
        filename, is_template = _STATUS_ICONS[key]
        # Order matters: rumps' template setter re-applies the current icon,
        # and its icon setter reads the current template flag.
        self.template = is_template
        self.icon = str(_ICON_DIR / filename)

    def _on_double_tap(self) -> None:
        if not self._ready:
            rumps.notification("vlow", "", "Model still loading…")
            return
        if self._state == State.IDLE:
            self._start_recording()
        elif self._state == State.RECORDING:
            self._stop_and_transcribe()
        else:
            # ignore taps while transcribing or streaming
            _log(f"double-tap ignored (state={self._state.value})")

    def _start_stream(self) -> None:
        # Hold gesture can fire while the user is also in a batch session —
        # ignore unless we're idle.
        if not self._ready or self._state != State.IDLE:
            _log(f"hold ignored (ready={self._ready}, state={self._state.value})")
            return
        self._to_state(State.STREAMING, "hold start")
        self._pasted_in_session = False
        self._last_text = ""
        # Preserve the user's clipboard for the whole streaming session so we
        # don't flicker it back-and-forth between finalized turns.
        self._preserved_clipboard = snapshot_clipboard()
        self._set_status_icon("recording")
        if self._overlay is not None:
            self._overlay.show_recording()
        self._stream = StreamingSession(
            on_final=self._on_stream_final,
            on_level=self._on_level,
            device=self._input_device,
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
        self._to_state(State.FINALIZING, "hold end")
        self._set_status_icon("busy")
        if self._overlay is not None:
            self._overlay.show_busy()
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
        self._set_status_icon("idle")
        self._to_state(State.IDLE, "stream finished")
        self._restore_preserved_clipboard()

    def _restore_preserved_clipboard(self) -> None:
        snap = self._preserved_clipboard
        if snap is None:
            return
        self._preserved_clipboard = None
        # Give the target app a beat to finish consuming the last paste
        # before we overwrite the pasteboard with the restored contents.
        time.sleep(POST_PASTE_WAIT_SEC)
        restore_clipboard(snap)

    def _on_level(self, rms: float) -> None:
        # Called from the audio callback thread; throttle to ~30 fps so the
        # main queue isn't flooded by small-blocksize devices.
        if self._overlay is None:
            return
        now = time.monotonic()
        if now - self._last_level_ts < 0.03:
            return
        self._last_level_ts = now
        on_main_thread(lambda: self._overlay.push_level(rms))

    def _on_stream_final(self, text: str) -> None:
        # Paste each final turn progressively so dictation appears live in the
        # focused app. Add a leading space between turns of the same session.
        if self._pasted_in_session:
            chunk = " " + text
        else:
            chunk = text
            self._pasted_in_session = True
        try:
            paste_no_restore(chunk)
        except Exception as e:
            print(f"live paste error: {e}", flush=True)
        self._last_text = (self._last_text + " " + text).strip() if self._last_text else text

    def _start_recording(self) -> None:
        self._to_state(State.RECORDING, "double-tap")
        self._set_status_icon("recording")
        if self._overlay is not None:
            self._overlay.show_recording()
        # Re-create the Recorder each session so device selection (and any
        # newly-attached BT mic) takes effect.
        self._recorder = Recorder(device=self._input_device, on_level=self._on_level)
        try:
            self._recorder.start()
        except Exception as e:
            print(f"failed to start audio: {e}")
            rumps.notification("vlow audio error", "", str(e))
            self._reset()

    def _stop_and_transcribe(self) -> None:
        self._to_state(State.TRANSCRIBING, "double-tap stop")
        self._set_status_icon("busy")
        if self._overlay is not None:
            self._overlay.show_busy()
        # recorder.stop() blocks ~110ms in PortAudio stream teardown — off
        # the main thread, or the overlay's transition drops frames.
        threading.Thread(target=self._do_transcribe, daemon=True).start()

    def _do_transcribe(self) -> None:
        text = ""
        try:
            audio = self._recorder.stop()
            # Persist the raw audio before transcribing so a crash in
            # MLX / AAI never loses the recording.
            try:
                save_float32(audio)
            except Exception as e:
                print(f"save raw recording failed: {e}", flush=True)
            text = transcribe(audio)
        except Exception as e:
            print(f"transcribe error: {e}")
        on_main_thread(lambda: self._finish(text))

    def _finish(self, text: str) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self._set_status_icon("idle")
        self._to_state(State.IDLE, f"transcription done, {len(text)} chars")
        if text:
            self._last_text = text
            paste(text)

    def _reset(self) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self._set_status_icon("idle")
        self._to_state(State.IDLE, "reset")
        self._restore_preserved_clipboard()
