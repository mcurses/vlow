from AppKit import (
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSTextField,
    NSTextAlignmentCenter,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakeRect


class Overlay:
    """Small floating, non-activating panel that shows recording status."""

    def __init__(self) -> None:
        screen = NSScreen.mainScreen().visibleFrame()
        w, h = 240, 56
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
        label.setFont_(NSFont.systemFontOfSize_(15))
        label.setFrame_(NSMakeRect(10, 16, w - 20, 24))
        content.addSubview_(label)

        self._panel = panel
        self._label = label

    def show(self, text: str) -> None:
        self._label.setStringValue_(text)
        self._panel.orderFront_(None)

    def update(self, text: str) -> None:
        self._label.setStringValue_(text)

    def hide(self) -> None:
        self._panel.orderOut_(None)
