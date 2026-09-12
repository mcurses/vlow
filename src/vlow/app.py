import sys
import threading
import traceback
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
from . import settings as settings_mod
from . import local_models, updater
from .config import load as load_config
from .diag import Watchdog, install_termination_hook
from .hotkey import EVENT_STATS, DoubleTapDetector, HoldDetector, TapHoldDetector
from .overlay import Overlay
from .resources import menubar_icon_dir
from .paste import (
    POST_PASTE_WAIT_SEC,
    paste,
    paste_no_restore,
    restore_clipboard,
    snapshot_clipboard,
)
from .recordings import LATEST_PATH as RECORDING_PATH, reveal_in_finder, save_float32, save_int16_bytes
from .replay import ReplayHotkey
from .settings_window import open_settings, set_model_status, set_update_progress, set_update_status
from .stream_aai import StreamingSession
from .transcribe import auto_threshold_sec, backend_name, transcribe, warmup


def _backend_label() -> str:
    name = backend_name()
    local = local_models.selected_key()
    if name == "auto":
        return f"Backend: auto ({local}, >{auto_threshold_sec():.0f}s → assemblyai)"
    if name == "mlx":
        return f"Backend: {local}"
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
    def guarded():
        try:
            fn()
        except Exception as e:  # an exception escaping into AppKit aborts the process
            _log(f"main-thread callback failed: {e!r}")

    NSOperationQueue.mainQueue().addOperationWithBlock_(guarded)


VALID_MODES = ("toggle", "ptt")
# ~29 level pushes/s (the 30 ms throttle gave ~32/s; 10% slower scroll of the
# recording waveform). Mic callbacks arrive far faster than this, so the
# throttle sets the rate.
LEVEL_PUSH_INTERVAL_SEC = 1 / 29

# Menubar status icons (SF Symbol renders, see scripts/gen-menubar-icons.py).
# key → (filename, is_template). Template icons adapt to menubar appearance;
# the recording icon stays system-red.
_ICON_DIR = menubar_icon_dir()
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
        if settings_mod.ensure_config_file():
            _log(f"created default config at {settings_mod.CONFIG_PATH}")
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
        self._replay = ReplayHotkey(lambda: self._last_text, self._config.get("repaste_hotkey", ""))
        self._ready = False
        self._model_prompted = False  # auto-open Settings for the download once per run
        self._update_busy = False
        self._update_offered: str | None = None  # version already shown by the auto-check

        self._hotkey = self._make_detector(self._mode, self._config["hotkey"])

        # Menubar fallbacks — reliable escape hatches if the hotkey misfires.
        self._mode_item = rumps.MenuItem(f"Mode: {self._mode}")
        self._mode_item.set_callback(None)
        self._backend_item = rumps.MenuItem(_backend_label())
        self._backend_item.set_callback(None)
        self._stop_item = rumps.MenuItem("Stop & Transcribe", callback=self._menu_stop)
        self._discard_item = rumps.MenuItem("Discard Recording", callback=self._menu_discard)
        self._replay_item = rumps.MenuItem("Re-paste Last", callback=self._menu_replay)
        self._reveal_item = rumps.MenuItem("Reveal Last Recording", callback=self._menu_reveal)
        self._settings_item = rumps.MenuItem("Settings…", callback=self._menu_settings, key=",")
        self._update_item = rumps.MenuItem("Check for Updates…", callback=self._menu_check_updates)
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
            self._settings_item,
            self._update_item,
            None,
        ]

        # NSEvent monitor + NSPanel + threads don't actually need NSApp.run()
        # to be active; both rumps.Timer and NSOperationQueue main-queue
        # one-shots were never firing on macOS 26, so run setup inline.
        self._deferred_setup(None)

    def _make_detector(self, mode: str, hotkey: str):
        if mode == "ptt":
            return HoldDetector(self._start_stream, self._stop_stream, hotkey=hotkey)
        # toggle — double-tap = batch, hold = streaming
        return TapHoldDetector(
            on_double_tap=self._on_double_tap,
            on_hold_start=self._start_stream,
            on_hold_end=self._stop_stream,
            hotkey=hotkey,
        )

    def _menu_settings(self, _) -> None:
        self._open_settings()

    def _open_settings(self) -> None:
        try:
            open_settings(settings_mod.current(), self._apply_settings, self._on_settings_action)
            for st in local_models.all_status():
                set_model_status(st)
        except Exception as e:
            _log(f"settings window failed: {e}")
            rumps.notification("vlow", "Settings unavailable", str(e))

    def _on_settings_action(self, name: str) -> None:
        _log(f"settings action: {name}")
        if name.startswith("downloadModel"):
            # "downloadModel:<key>" from the per-model rows; bare form → selected.
            _, _, key = name.partition(":")
            model = local_models.MODELS.get(key) or local_models.selected()
            if local_models.is_downloading():
                return
            threading.Thread(target=self._download_model, args=(model,), daemon=True).start()
        elif name == "checkUpdates":
            self._check_updates(interactive=True)

    # --- updates ---------------------------------------------------------

    def _menu_check_updates(self, _) -> None:
        self._check_updates(interactive=True)

    def _check_updates(self, interactive: bool) -> None:
        if self._update_busy:
            return
        self._update_busy = True
        self._set_update_status("Checking…")
        threading.Thread(target=self._do_check_updates, args=(interactive,), daemon=True).start()

    def _do_check_updates(self, interactive: bool) -> None:
        try:
            info = updater.check()
        except updater.UpdateError as e:
            msg = str(e)  # bind now: `e` is gone once the except block ends
            _log(f"update check failed: {msg}")
            self._update_busy = False
            self._set_update_status(msg)
            if interactive:
                on_main_thread(lambda: rumps.alert("Check for Updates", msg))
            return
        self._update_busy = False
        if not info["is_newer"]:
            _log(f"up to date ({info['current']})")
            self._set_update_status(f"You're up to date ({info['current']}).")
            if interactive:
                on_main_thread(
                    lambda: rumps.alert("You're up to date", f"vlow {info['current']} is the latest version.")
                )
            return
        _log(f"update available: {info['current']} → {info['latest']}")
        self._set_update_status(f"Version {info['latest']} is available.")
        if not interactive and self._update_offered == info["latest"]:
            return
        self._update_offered = info["latest"]
        on_main_thread(lambda: self._offer_update(info))

    def _offer_update(self, info: dict) -> None:
        kind = updater.install_kind()
        if kind == "bundle":
            how = (
                "vlow downloads the update, replaces itself and relaunches. "
                "macOS will ask for Accessibility again."
            )
        elif kind == "source":
            how = (
                f"This copy runs from the source checkout at {updater.source_checkout()}: "
                "vlow pulls the latest commit, runs uv sync, rebuilds the app bundle and restarts."
            )
        else:
            choice = rumps.alert(
                f"vlow {info['latest']} is available",
                f"You have {info['current']}. This copy can't update itself, so grab the new "
                "DMG from GitHub.",
                ok="Open Releases",
                cancel="Later",
            )
            if choice == 1:
                import subprocess as _sp

                _sp.run(["open", info["notes_url"]], check=False)
            return
        choice = rumps.alert(
            f"vlow {info['latest']} is available",
            f"You have {info['current']}. Install it now? {how}",
            ok="Install and Relaunch",
            cancel="Later",
        )
        if choice == 1:
            threading.Thread(target=self._install_update, args=(info,), daemon=True).start()

    def _install_update(self, info: dict) -> None:
        if self._update_busy:
            return
        if self._state is not State.IDLE:
            on_main_thread(
                lambda: rumps.alert("Update postponed", "Finish the current recording first, then check again.")
            )
            return
        self._update_busy = True
        on_main_thread(lambda: self._set_status_icon("busy"))
        rumps.notification("vlow", f"Updating to {info['latest']}…", "vlow relaunches when it's done.")
        self._set_update_progress(None, "Starting…")
        try:
            updater.install_update(info, on_progress=self._set_update_progress)
        except updater.UpdateError as e:
            msg = str(e)
            _log(f"update failed: {msg}")
            self._update_busy = False
            self._set_update_progress(None, f"Update failed: {msg}", visible=False)
            on_main_thread(lambda: self._set_status_icon("idle" if self._ready else "error"))
            on_main_thread(lambda: rumps.alert("Update failed", msg))

    def _set_update_progress(self, fraction: float | None, text: str, visible: bool = True) -> None:
        """Mirror install progress into Settings (bar + caption) and the
        menubar item, so it is visible even with the window closed."""
        def push() -> None:
            if visible:
                pct = f" {fraction:.0%}" if fraction is not None and fraction < 1 else ""
                self._update_item.title = f"Updating…{pct}"
            else:
                self._update_item.title = "Check for Updates…"
            try:
                set_update_status(text)
                set_update_progress(fraction, visible)
            except Exception:
                pass  # window never opened / dylib missing — status is only cosmetic

        on_main_thread(push)

    def _set_update_status(self, text: str) -> None:
        self._set_update_progress(None, text, visible=False)

    def _auto_update_loop(self) -> None:
        """Daily background check, opt-out via Settings → Updates."""
        time.sleep(45)  # let warmup and the first-run prompts settle
        while True:
            try:
                if settings_mod.current().get("check_updates", True):
                    self._check_updates(interactive=False)
            except Exception as e:
                _log(f"auto update check error: {e}")
            time.sleep(24 * 3600)

    def _download_model(self, model: local_models.LocalModel) -> None:
        def push(st: dict) -> None:
            on_main_thread(lambda: set_model_status(st))

        try:
            local_models.download(model, push)
        except Exception as e:
            _log(f"{model.key} download failed: {e}")
            rumps.notification("vlow", f"{model.display} download failed", str(e))
            return
        _log(f"{model.key} downloaded ({local_models.size_on_disk(model) / 1e9:.1f} GB)")
        if model.key == local_models.selected_key():
            rumps.notification("vlow", f"{model.display} ready", "Loading it now…")
            self._warmup()
        else:
            rumps.notification(
                "vlow", f"{model.display} ready", "Select it under On-device model to use it."
            )

    def _needs_model(self) -> bool:
        return self._mode != "ptt" and backend_name() in ("mlx", "auto")

    def _apply_settings(self, data: dict) -> None:
        """Called (main thread) for every debounced edit in the Settings window."""
        before = settings_mod.current()
        try:
            new = settings_mod.normalize(data)
        except ValueError as e:
            _log(f"settings rejected: {e}")
            return
        settings_mod.save(new)
        settings_mod.apply_env(new)
        self._config = load_config()
        changed = {k for k in new if new[k] != before.get(k)}
        _log(f"settings saved ({', '.join(sorted(changed)) or 'no change'})")

        if changed & {"hotkey", "mode"}:
            try:
                self._hotkey.stop()
            except Exception as e:
                _log(f"hotkey stop failed: {e}")
            self._mode = new["mode"]
            self._mode_item.title = f"Mode: {self._mode}"
            self._hotkey = self._make_detector(new["mode"], new["hotkey"])
            try:
                self._hotkey.start()
                _log(f"hotkey monitor restarted ({type(self._hotkey).__name__}, {new['hotkey']})")
            except Exception as e:
                _log(f"hotkey restart failed: {e}")
        if "repaste_hotkey" in changed:
            try:
                self._replay.set_hotkey(new["repaste_hotkey"])
                _log(f"replay hotkey now {new['repaste_hotkey'] or 'none'}")
            except Exception as e:
                _log(f"replay hotkey change failed: {e}")
        if changed & {"backend", "local_model", "auto_threshold_sec"}:
            self._backend_item.title = _backend_label()
        if changed & {"backend", "local_model", "mode", "assemblyai_api_key"}:
            # A new backend may need its model loaded / key verified.
            self._ready = False
            self._set_status_icon("loading")
            threading.Thread(target=self._warmup, daemon=True).start()

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
            _log(f"replay hotkey started ({self._replay.hotkey or 'none'})")
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
        try:
            install_termination_hook(self.emergency_save)
        except Exception as e:
            _log(f"termination hook failed to install: {e}")
        threading.Thread(target=self._auto_update_loop, daemon=True).start()

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
            elif self._needs_model() and not local_models.is_downloaded(local_models.selected()):
                # Never pull gigabytes behind the user's back: point them at the
                # Download button instead (and open Settings the first time).
                model = local_models.selected()
                _log(f"{model.key} not downloaded — waiting for the user")
                on_main_thread(lambda: self._set_status_icon("error"))
                rumps.notification(
                    f"vlow needs {model.display}",
                    f"One-time download, about {model.approx_bytes / 1e9:.1f} GB",
                    "Open Settings → On-device model → Download.",
                )
                if not self._model_prompted:
                    self._model_prompted = True
                    on_main_thread(self._open_settings)
                return
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
        # Called from the audio callback thread; throttle so the main queue
        # isn't flooded by small-blocksize devices. Each push shifts the
        # overlay bars one step, so this interval is also the scroll speed
        # of the recording waveform (keep LEVEL_PUSH_HZ in VlowGlass.swift
        # in sync).
        if self._overlay is None:
            return
        now = time.monotonic()
        if now - self._last_level_ts < LEVEL_PUSH_INTERVAL_SEC:
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
            # stdout is a file under launchd (block-buffered): flush, or the
            # error sits in the buffer while the log shows "0 chars".
            _log(f"transcribe error: {e!r}")
            traceback.print_exc()
            sys.stderr.flush()
        on_main_thread(lambda: self._finish(text))

    def _finish(self, text: str) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self._set_status_icon("idle")
        self._to_state(State.IDLE, f"transcription done, {len(text)} chars")
        if text:
            self._last_text = text
            paste(text)

    def emergency_save(self) -> None:
        """SIGTERM while capturing: write whatever audio exists so far to
        last_recording.wav. Runs on the termination thread, touches no UI.
        Transcribing/finalizing states already saved before they started."""
        state = self._state
        if state is State.RECORDING:
            audio = self._recorder.snapshot()
            path = save_float32(audio)
            _log(f"emergency save: {audio.size / 16000:.1f}s of recording → {path}")
        elif state is State.STREAMING and self._stream is not None:
            pcm = self._stream.snapshot_pcm16()
            path = save_int16_bytes(pcm)
            _log(f"emergency save: {len(pcm) / 32000:.1f}s of stream → {path}")
        else:
            _log(f"emergency save: nothing in flight (state={state.value})")

    def _reset(self) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self._set_status_icon("idle")
        self._to_state(State.IDLE, "reset")
        self._restore_preserved_clipboard()
