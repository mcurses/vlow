import math
import threading
import time

import objc
from AppKit import (
    NSAppearance,
    NSAppearanceNameDarkAqua,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSGlassEffectView,
    NSGraphicsContext,
    NSPanel,
    NSShadow,
    NSScreen,
    NSStatusWindowLevel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowDidMoveNotification,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import (
    NSAnimationContext,
    NSMakeRect,
    NSNotificationCenter,
    NSOperationQueue,
    NSPointInRect,
    NSUserDefaults,
)
from Quartz import CABasicAnimation, CASpringAnimation

_METER_BARS = 28
# RMS of normal speech at a typical mic distance sits around 0.03–0.15;
# divide by this before the perceptual sqrt so voice spans most of the bar.
_METER_FULL_SCALE_RMS = 0.25
_WAVE_FPS = 30.0


def _on_main(fn):
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


class _MeterView(NSView):
    """The pill's only content: a row of rounded bars.

    mode "levels": bars scroll right-to-left with live mic amplitude.
    mode "wave":   bars ripple with a traveling sine wave (transcribing).
    """

    def initWithFrame_(self, frame):
        self = objc.super(_MeterView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._levels = [0.0] * _METER_BARS
        self._mode = "levels"
        self._phase = 0.0
        return self

    def setMode_(self, mode):
        self._mode = mode
        if mode == "levels":
            self._levels = [0.0] * _METER_BARS
        self.setNeedsDisplay_(True)

    def pushLevel_(self, level):
        # Blend with the previous newest bar so the scroll reads as one
        # continuous waveform instead of disconnected samples.
        level = min(1.0, max(0.0, float(level)))
        smoothed = max(level, self._levels[-1] * 0.72)
        self._levels = self._levels[1:] + [smoothed]
        if self._mode == "levels":
            self.setNeedsDisplay_(True)

    def advanceWave_(self, dt):
        self._phase += dt * 2.6
        if self._mode == "wave":
            self.setNeedsDisplay_(True)

    def drawRect_(self, _rect):
        bounds = self.bounds()
        n = _METER_BARS
        gap = 2.5
        bar_w = (bounds.size.width - gap * (n - 1)) / n
        radius = bar_w / 2.0
        # Aurora gradient (violet → cyan) with a soft dark halo per bar:
        # over clear glass no single color survives every backdrop, but
        # color + contrast shadow reads everywhere, like subtitles.
        NSGraphicsContext.saveGraphicsState()
        shadow = NSShadow.alloc().init()
        shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.75))
        shadow.setShadowBlurRadius_(4.0)
        shadow.setShadowOffset_((0.0, -0.5))
        shadow.set()
        for i in range(n):
            if self._mode == "wave":
                level = 0.30 + 0.24 * math.sin(self._phase + i * 0.48)
            else:
                level = self._levels[i]
            # Fade the outermost bars so the row melts into the glass.
            edge = min(1.0, (i + 1) / 4.0, (n - i) / 4.0)
            t = i / (n - 1)
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.48 + (0.12 - 0.48) * t,
                0.30 + (0.78 - 0.30) * t,
                0.98,
                edge,
            ).setFill()
            h = max(bar_w, level * bounds.size.height)
            x = i * (bar_w + gap)
            y = (bounds.size.height - h) / 2.0
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, bar_w, h), radius, radius
            ).fill()
        NSGraphicsContext.restoreGraphicsState()


class _DotView(NSView):
    """Small record dot; pulses via a repeating CA opacity animation."""

    def drawRect_(self, _rect):
        NSGraphicsContext.saveGraphicsState()
        shadow = NSShadow.alloc().init()
        shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.6))
        shadow.setShadowBlurRadius_(3.0)
        shadow.setShadowOffset_((0.0, -0.5))
        shadow.set()
        NSColor.systemRedColor().setFill()
        NSBezierPath.bezierPathWithOvalInRect_(self.bounds()).fill()
        NSGraphicsContext.restoreGraphicsState()

    def startPulse(self):
        self.setWantsLayer_(True)
        pulse = CABasicAnimation.animationWithKeyPath_("opacity")
        pulse.setFromValue_(1.0)
        pulse.setToValue_(0.25)
        pulse.setDuration_(0.7)
        pulse.setAutoreverses_(True)
        pulse.setRepeatCount_(float("inf"))
        self.layer().addAnimation_forKey_(pulse, "pulse")


class Overlay:
    """Floating, non-activating liquid-glass pill: pure animation, no text.

    Recording → live amplitude bars + pulsing red dot.
    Busy (transcribing/finalizing) → traveling wave, dot hidden.
    Open/close/state-switch spring-animate like iOS glass controls.
    """

    _W, _H = 200, 52
    _ORIGIN_KEY = "overlayOrigin"  # NSUserDefaults (com.vlow): [x, y]

    def __init__(self) -> None:
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
        panel.setHasShadow_(True)
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

        # Clear liquid glass (macOS 26): untinted so the rim lensing and
        # backdrop transmission stay visible — the bars carry their own
        # contrast (halo shadows) instead of a legibility tint.
        glass = NSGlassEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        glass.setCornerRadius_(h / 2.0)
        glass.setStyle_(1)  # NSGlassEffectViewStyleClear
        glass.setWantsLayer_(True)
        panel.contentView().addSubview_(glass)

        inner = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        meter = _MeterView.alloc().initWithFrame_(NSMakeRect(42, 12, w - 62, h - 24))
        inner.addSubview_(meter)
        dot = _DotView.alloc().initWithFrame_(NSMakeRect(20, h / 2 - 4, 8, 8))
        inner.addSubview_(dot)
        glass.setContentView_(inner)

        self._panel = panel
        self._glass = glass
        self._meter = meter
        self._dot = dot
        self._mode: str | None = None  # None | "record" | "busy"
        self._wave_thread: threading.Thread | None = None

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

    # ── animations ──────────────────────────────────────────────────────

    def _spring(self, from_scale: float, damping: float = 13.0) -> None:
        layer = self._glass.layer()
        layer.setAnchorPoint_((0.5, 0.5))
        layer.setPosition_((self._W / 2, self._H / 2))
        spring = CASpringAnimation.animationWithKeyPath_("transform.scale")
        spring.setFromValue_(from_scale)
        spring.setToValue_(1.0)
        spring.setDamping_(damping)
        spring.setStiffness_(240.0)
        spring.setMass_(1.0)
        spring.setInitialVelocity_(0.0)
        spring.setDuration_(spring.settlingDuration())
        layer.addAnimation_forKey_(spring, "pop")

    def _start_wave(self) -> None:
        if self._wave_thread is not None:
            return

        def run():
            dt = 1.0 / _WAVE_FPS
            while self._mode == "busy":
                _on_main(lambda: self._meter.advanceWave_(dt))
                time.sleep(dt)
            self._wave_thread = None

        self._wave_thread = threading.Thread(target=run, daemon=True)
        self._wave_thread.start()

    # ── public API (main thread) ────────────────────────────────────────

    def show_recording(self) -> None:
        """Pop the pill in with live amplitude bars + pulsing record dot."""
        self._mode = "record"
        self._meter.setMode_("levels")
        self._dot.setHidden_(False)
        self._dot.startPulse()
        if not self._panel.isVisible():
            self._panel.setAlphaValue_(0.0)
            self._panel.orderFront_(None)
            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.22)
            self._panel.animator().setAlphaValue_(1.0)
            NSAnimationContext.endGrouping()
            self._spring(0.45)

    def show_busy(self) -> None:
        """Switch to the transcribing wave with a springy squish."""
        was_visible = self._panel.isVisible()
        self._mode = "busy"
        self._meter.setMode_("wave")
        self._dot.setHidden_(True)
        if not was_visible:
            self._panel.setAlphaValue_(1.0)
            self._panel.orderFront_(None)
            self._spring(0.45)
        else:
            self._spring(0.90, damping=9.0)
        self._start_wave()

    def push_level(self, rms: float) -> None:
        """Feed one raw RMS sample (0.0–1.0); perceptually scaled here."""
        self._meter.pushLevel_((rms / _METER_FULL_SCALE_RMS) ** 0.5)

    def hide(self) -> None:
        if not self._panel.isVisible():
            self._mode = None
            return
        self._mode = None  # stops the wave thread
        shrink = CABasicAnimation.animationWithKeyPath_("transform.scale")
        shrink.setFromValue_(1.0)
        shrink.setToValue_(0.75)
        shrink.setDuration_(0.16)
        self._glass.layer().addAnimation_forKey_(shrink, "shrink")

        def done():
            self._panel.orderOut_(None)
            self._panel.setAlphaValue_(1.0)
            self._glass.layer().removeAllAnimations()

        def fade(ctx):
            ctx.setDuration_(0.16)
            self._panel.animator().setAlphaValue_(0.0)

        NSAnimationContext.runAnimationGroup_completionHandler_(fade, done)
