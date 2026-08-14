"""Render the menubar status icons from SF Symbols into assets/menubar/.

Run: uv run python scripts/gen-menubar-icons.py
Outputs 80x80 PNGs (rumps scales them to 20pt in the status bar):
  mic.png      idle          (template)
  mic-dim.png  model loading (template, 40% alpha)
  mic-red.png  recording     (color, system red)
  waveform.png transcribing  (template)
  warn.png     warmup failed (template)
"""

from pathlib import Path

from AppKit import (
    NSBitmapImageRep,
    NSColor,
    NSCompositingOperationSourceOver,
    NSFontWeightRegular,
    NSGraphicsContext,
    NSImage,
    NSImageSymbolConfiguration,
    NSPNGFileType,
)
from Foundation import NSMakeRect

OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "menubar"
CANVAS = 80  # px; drawn glyph is scaled to fit with a little padding


def render(symbol: str, out_name: str, color=None, alpha: float = 1.0) -> None:
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, None)
    if img is None:
        raise SystemExit(f"SF Symbol not found: {symbol}")
    cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
        64, NSFontWeightRegular
    )
    if color is not None:
        cfg = cfg.configurationByApplyingConfiguration_(
            NSImageSymbolConfiguration.configurationWithPaletteColors_([color])
        )
    img = img.imageWithSymbolConfiguration_(cfg)

    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, CANVAS, CANVAS, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    # Fit the glyph into the canvas preserving aspect ratio, centered.
    size = img.size()
    pad = 4
    scale = min((CANVAS - 2 * pad) / size.width, (CANVAS - 2 * pad) / size.height)
    w, h = size.width * scale, size.height * scale
    img.drawInRect_fromRect_operation_fraction_(
        NSMakeRect((CANVAS - w) / 2, (CANVAS - h) / 2, w, h),
        NSMakeRect(0, 0, size.width, size.height),
        NSCompositingOperationSourceOver,
        alpha,
    )
    NSGraphicsContext.restoreGraphicsState()

    out = OUT_DIR / out_name
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(
        str(out), True
    )
    print(f"wrote {out}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render("mic.fill", "mic.png")
    render("mic.fill", "mic-dim.png", alpha=0.4)
    render("mic.fill", "mic-red.png", color=NSColor.systemRedColor())
    render("waveform", "waveform.png")
    render("exclamationmark.triangle.fill", "warn.png")


if __name__ == "__main__":
    main()
