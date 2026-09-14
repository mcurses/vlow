import ctypes
import threading
import time

import objc
from AppKit import (
    NSAppearance,
    NSAppearanceNameDarkAqua,
    NSBackingStoreBuffered,
    NSColor,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowDidMoveNotification,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import (
    NSMakeRect,
    NSNotificationCenter,
    NSOperationQueue,
    NSPointInRect,
    NSUserDefaults,
)

from .resources import glass_dylib

_DYLIB = glass_dylib()
_HIDE_DELAY_SEC = 0.55  # let the dematerialize transition finish first


def _on_main(fn):
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


class Overlay:
    """Floating, non-activating liquid-glass pill: pure animation, no text.

    The pill itself is SwiftUI (native/VlowGlass.swift → libVlowGlass.dylib):
    clear glass capsule, aurora amplitude bars, and the real materialize /
    dematerialize glass transitions on show/hide. Python owns the panel —
    position, Spaces behavior, dragging — and feeds mic levels to the model.
    """

    _W, _H = 232, 68  # 200x52 pill + margin for the materialize wobble
    _ORIGIN_KEY = "overlayOrigin"  # NSUserDefaults (com.vlow): [x, y]

    def __init__(self) -> None:
        ctypes.CDLL(str(_DYLIB))  # OSError here → run scripts/build-glass.sh
        glass_cls = objc.lookUpClass("VlowGlass")
        self._model = glass_cls.makeModel()

        screen = NSScreen.mainScreen().visibleFrame()
        w, h = self._W, self._H
        x, y = self._restore_origin() or (
            screen.origin.x + (screen.size.width - w) / 2,
            screen.origin.y + screen.size.height * 0.18,
        )
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h), style, NSBackingStoreBuffered, False
        )
        panel.setLevel_(NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(False)  # the glass draws its own edge treatment
        panel.setHidesOnDeactivate_(False)
        # Follow the user across Spaces (and over fullscreen apps), and let
        # them drag the pill anywhere — the position sticks via NSUserDefaults.
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        panel.setIgnoresMouseEvents_(False)
        panel.setMovableByWindowBackground_(True)
        NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            NSWindowDidMoveNotification, panel, None, self._on_moved
        )
        panel.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameDarkAqua))

        view = glass_cls.makeView_(self._model)
        view.setFrame_(NSMakeRect(0, 0, w, h))
        panel.contentView().addSubview_(view)

        self._panel = panel
        self._view = view
        self._peak = 0.04  # rolling loudness for display auto-gain
        self._hide_seq = 0
        self._jobs: list[str] = []
        self._mode = "hidden"
        self._glass_cls = glass_cls

    # ── position persistence ────────────────────────────────────────────

    def _restore_origin(self):
        """Return the saved (x, y) if it still lands on a screen, else None."""
        stored = NSUserDefaults.standardUserDefaults().arrayForKey_(self._ORIGIN_KEY)
        if not stored or len(stored) != 2:
            return None
        x, y = float(stored[0]), float(stored[1])
        center = (x + self._W / 2, y + self._H / 2)
        for screen in NSScreen.screens():
            if NSPointInRect(center, screen.visibleFrame()):
                return x, y
        return None

    def _on_moved(self, _note) -> None:
        origin = self._panel.frame().origin
        NSUserDefaults.standardUserDefaults().setObject_forKey_(
            [float(origin.x), float(origin.y)], self._ORIGIN_KEY
        )

    # ── public API (main thread) ────────────────────────────────────────

    def show_recording(self) -> None:
        """Materialize the pill with live amplitude bars."""
        self._hide_seq += 1  # cancel any pending order-out
        self._peak = 0.04
        self._mode = "record"
        self._resize()  # make room before the pill materializes into it
        self._panel.orderFront_(None)
        self._model.setMode_("record")

    def show_busy(self) -> None:
        """Morph to the transcribing wave."""
        self._hide_seq += 1
        self._mode = "busy"
        self._resize()
        self._panel.orderFront_(None)
        self._model.setMode_("busy")

    def set_jobs(self, ids: list[str]) -> None:
        """Show one glass blob per in-flight transcription, oldest first.

        The blobs bud out of the pill's left edge, so the panel grows to the
        left and its right edge stays pinned — the pill never drifts across
        the screen while jobs come and go.
        """
        ids = list(ids)
        if ids == self._jobs:
            return
        growing = len(ids) > len(self._jobs)
        self._jobs = ids
        if ids:
            self._hide_seq += 1  # cancel a pending order-out
            self._panel.orderFront_(None)
        # Grow the panel before the blob animates in (or it would be clipped),
        # but shrink only after the outgoing blob has finished dissolving.
        if growing:
            self._resize(len(ids))
            self._model.setJobs_(ids)
        else:
            self._model.setJobs_(ids)
            self._after(_HIDE_DELAY_SEC, lambda: self._resize(len(self._jobs)))
            self._maybe_order_out()

    def _resize(self, *_ignored) -> None:
        """Size the panel to whatever is currently on it, pinning the right
        edge so the pill never drifts across the screen."""
        width = float(
            self._glass_cls.viewWidthForJobCount_pillVisible_(
                len(self._jobs), self._mode != "hidden"
            )
        )
        frame = self._panel.frame()
        # Pin the right edge: x moves left by exactly the width we gained.
        x = frame.origin.x + frame.size.width - width
        self._panel.setFrame_display_animate_(
            NSMakeRect(x, frame.origin.y, width, frame.size.height), True, False
        )
        self._view.setFrame_(NSMakeRect(0, 0, width, frame.size.height))

    @staticmethod
    def _after(delay: float, fn) -> None:
        def later():
            time.sleep(delay)
            _on_main(fn)

        threading.Thread(target=later, daemon=True).start()

    def push_level(self, rms: float) -> None:
        """Feed one raw RMS sample; display is auto-gained to recent peak
        so quiet mics still fill the bars."""
        self._peak = max(rms, self._peak * 0.995, 0.04)
        self._model.pushLevel_(min(1.0, (rms / self._peak) ** 0.7))

    def hide(self) -> None:
        """Dematerialize the pill. Blobs for still-queued transcriptions stay
        up; the panel only leaves once nothing at all is left to show."""
        self._mode = "hidden"
        self._model.setMode_("hidden")  # plays the dematerialize transition
        # Reclaim the pill's width only once it has finished dissolving.
        self._after(_HIDE_DELAY_SEC, self._resize)
        self._maybe_order_out()

    def _maybe_order_out(self) -> None:
        self._hide_seq += 1
        if self._mode != "hidden" or self._jobs:
            return
        seq = self._hide_seq
        self._after(_HIDE_DELAY_SEC, lambda: self._order_out_if(seq))

    def _order_out_if(self, seq: int) -> None:
        if seq == self._hide_seq:
            self._panel.orderOut_(None)
            self._resize(0)  # back to base width for the next materialize
