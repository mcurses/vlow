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
        self._peak = 0.04  # rolling loudness for display auto-gain
        self._hide_seq = 0

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
        self._panel.orderFront_(None)
        self._model.setMode_("record")

    def show_busy(self) -> None:
        """Morph to the transcribing wave."""
        self._hide_seq += 1
        self._panel.orderFront_(None)
        self._model.setMode_("busy")

    def push_level(self, rms: float) -> None:
        """Feed one raw RMS sample; display is auto-gained to recent peak
        so quiet mics still fill the bars."""
        self._peak = max(rms, self._peak * 0.995, 0.04)
        self._model.pushLevel_(min(1.0, (rms / self._peak) ** 0.7))

    def hide(self) -> None:
        self._model.setMode_("hidden")  # plays the dematerialize transition
        self._hide_seq += 1
        seq = self._hide_seq

        def later():
            time.sleep(_HIDE_DELAY_SEC)
            _on_main(lambda: self._order_out_if(seq))

        threading.Thread(target=later, daemon=True).start()

    def _order_out_if(self, seq: int) -> None:
        if seq == self._hide_seq:
            self._panel.orderOut_(None)
