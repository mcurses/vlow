import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSTextField,
    NSTextAlignmentCenter,
    NSView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakeRect

_METER_BARS = 20
# RMS of normal speech at a typical mic distance sits around 0.03–0.15;
# divide by this before the perceptual sqrt so voice spans most of the bar.
_METER_FULL_SCALE_RMS = 0.25


class _LevelMeterView(NSView):
    """Row of rounded vertical bars scrolling right-to-left with recent
    mic amplitude — the ChatGPT-recording-mode look."""

    def initWithFrame_(self, frame):
        self = objc.super(_LevelMeterView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._levels = [0.0] * _METER_BARS
        return self

    def reset(self):
        self._levels = [0.0] * _METER_BARS
        self.setNeedsDisplay_(True)

    def pushLevel_(self, level):
        self._levels = self._levels[1:] + [min(1.0, max(0.0, float(level)))]
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect):
        bounds = self.bounds()
        n = len(self._levels)
        gap = 2.0
        bar_w = (bounds.size.width - gap * (n - 1)) / n
        radius = bar_w / 2.0
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.9).setFill()
        for i, level in enumerate(self._levels):
            h = max(bar_w, level * bounds.size.height)  # floor: a dot, not nothing
            x = i * (bar_w + gap)
            y = (bounds.size.height - h) / 2.0
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, bar_w, h), radius, radius
            ).fill()


class Overlay:
    """Small floating, non-activating panel that shows recording status."""

    _W, _H = 240, 64
    _LABEL_TOP = NSMakeRect(10, 36, _W - 20, 20)      # meter visible below
    _LABEL_CENTERED = NSMakeRect(10, (_H - 22) / 2, _W - 20, 22)

    def __init__(self) -> None:
        screen = NSScreen.mainScreen().visibleFrame()
        w, h = self._W, self._H
        x = screen.origin.x + (screen.size.width - w) / 2
        y = screen.origin.y + screen.size.height * 0.18
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h), style, NSBackingStoreBuffered, False
        )
        panel.setLevel_(NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.85))
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        content = panel.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(12.0)
        content.layer().setMasksToBounds_(True)

        label = NSTextField.labelWithString_("")
        label.setTextColor_(NSColor.whiteColor())
        label.setBackgroundColor_(NSColor.clearColor())
        label.setDrawsBackground_(False)
        label.setBezeled_(False)
        label.setAlignment_(NSTextAlignmentCenter)
        label.setFont_(NSFont.systemFontOfSize_(14))
        label.setFrame_(self._LABEL_TOP)
        content.addSubview_(label)

        meter = _LevelMeterView.alloc().initWithFrame_(NSMakeRect(70, 10, 100, 20))
        content.addSubview_(meter)

        self._panel = panel
        self._label = label
        self._meter = meter

    def show(self, text: str) -> None:
        self._label.setStringValue_(text)
        self.set_meter_visible(True)
        self._meter.reset()
        self._panel.orderFront_(None)

    def update(self, text: str) -> None:
        self._label.setStringValue_(text)

    def push_level(self, rms: float) -> None:
        """Feed one raw RMS sample (0.0–1.0); perceptually scaled here."""
        self._meter.pushLevel_((rms / _METER_FULL_SCALE_RMS) ** 0.5)

    def set_meter_visible(self, visible: bool) -> None:
        self._meter.setHidden_(not visible)
        self._label.setFrame_(self._LABEL_TOP if visible else self._LABEL_CENTERED)

    def hide(self) -> None:
        self._panel.orderOut_(None)
