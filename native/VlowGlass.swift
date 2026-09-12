// Liquid-glass overlay pill rendered with SwiftUI's native glass APIs.
//
// Compiled to dist/libVlowGlass.dylib by scripts/build-glass.sh and loaded
// from Python (vlow/overlay.py) via dlopen + the ObjC runtime. The Python
// side owns the NSPanel (position, Spaces behavior, drag); this module owns
// everything drawn inside it, including the materialize/dematerialize
// "blub" transitions that AppKit's NSGlassEffectView cannot do.

import AppKit
import SwiftUI

private let barCount = 28
private let pillSize = CGSize(width: 200, height: 52)
// Rate at which Python pushes mic levels (one bar shift each); mirrors
// LEVEL_PUSH_INTERVAL_SEC in vlow/app.py so the outgoing snapshot keeps
// scrolling at the same speed as the live bars.
private let levelPushHz = 29.0

@objc(VlowGlassModel)
public final class VlowGlassModel: NSObject, ObservableObject {
    // "hidden" | "record" | "busy" — main thread only.
    @Published var mode: String = "hidden"
    var previousMode: String = "hidden"
    var modeChangedAt: TimeInterval = 0
    var levels: [Double] = Array(repeating: 0, count: barCount)

    @objc public func setMode(_ mode: String) {
        previousMode = self.mode
        modeChangedAt = Date().timeIntervalSinceReferenceDate
        withAnimation(.spring(response: 0.42, dampingFraction: 0.74)) {
            self.mode = mode
        }
        if mode == "record" {
            levels = Array(repeating: 0, count: barCount)
        }
    }

    @objc public func pushLevel(_ value: Double) {
        levels.removeFirst()
        // Blend with the neighbor so the scroll reads as one waveform.
        levels.append(max(min(1, max(0, value)), (levels.last ?? 0) * 0.72))
    }
}

private struct BarsView: View {
    @ObservedObject var model: VlowGlassModel

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 40.0)) { context in
            Canvas { g, size in
                let t = context.date.timeIntervalSinceReferenceDate
                let gap = 2.5
                let barW = (size.width - gap * Double(barCount - 1)) / Double(barCount)
                g.addFilter(.shadow(color: .black.opacity(0.7), radius: 4, y: 0.5))
                let elapsed = t - model.modeChangedAt
                // Wave phase is the integral of the smootherstep ramp, so the
                // wave starts stationary and accelerates C²-smoothly to full
                // speed instead of popping in at 7 rad/s.
                // ∫₀ᵖ (6u⁵−15u⁴+10u³) du = p⁶ − 3p⁵ + 2.5p⁴  (= 0.5 at p = 1)
                let rampT = 0.45
                let rp = min(1.0, max(0.0, elapsed / rampT))
                let rampIntegral = rp * rp * rp * rp * (2.5 + rp * (rp - 3.0))
                let phase = 7.0 * (rampT * rampIntegral + max(0.0, elapsed - rampT))
                // The outgoing recording snapshot keeps scrolling out to the
                // left (index shift at the live push cadence) so bar motion
                // never freezes while the wave sweeps in.
                let scrollShift = Int(elapsed * levelPushHz)
                func source(_ mode: String, _ i: Int, scrolled: Bool) -> Double {
                    switch mode {
                    case "busy": return 0.30 + 0.24 * sin(phase + Double(i) * 0.48)
                    case "record":
                        let j = scrolled ? i + scrollShift : i
                        return j < barCount ? model.levels[j] : 0
                    default: return 0
                    }
                }
                // Per-bar stagger sweeps the morph left→right; smootherstep
                // (Perlin quintic) is C² — curvature eases in and out of the
                // transition with no jerk at either end.
                for i in 0..<barCount {
                    let p = min(1.0, max(0.0, (elapsed - Double(i) * 0.012) / 0.45))
                    let blend = p * p * p * (p * (p * 6 - 15) + 10)
                    let level = source(model.previousMode, i, scrolled: model.previousMode == "record") * (1 - blend)
                        + source(model.mode, i, scrolled: false) * blend
                    let edge = min(1.0, Double(i + 1) / 4.0, Double(barCount - i) / 4.0)
                    let f = Double(i) / Double(barCount - 1)
                    let color = Color(
                        red: 0.48 + (0.12 - 0.48) * f,
                        green: 0.30 + (0.78 - 0.30) * f,
                        blue: 0.98
                    ).opacity(edge)
                    let h = max(barW, level * size.height)
                    let rect = CGRect(
                        x: Double(i) * (barW + gap),
                        y: (size.height - h) / 2,
                        width: barW,
                        height: h
                    )
                    g.fill(Path(roundedRect: rect, cornerRadius: barW / 2), with: .color(color))
                }
            }
        }
        .frame(width: 156, height: 28)
    }
}

private struct PillView: View {
    @ObservedObject var model: VlowGlassModel

    var body: some View {
        GlassEffectContainer {
            ZStack {
                if model.mode != "hidden" {
                    BarsView(model: model)
                        .frame(width: pillSize.width, height: pillSize.height)
                        .glassEffect(.clear, in: .capsule)
                        .glassEffectTransition(.materialize)
                }
            }
        }
        .frame(width: pillSize.width + 32, height: pillSize.height + 16)
    }
}

private final class DraggableHostingView<Content: View>: NSHostingView<Content> {
    override var mouseDownCanMoveWindow: Bool { true }

    @MainActor required init(rootView: Content) {
        super.init(rootView: rootView)
    }

    @MainActor required init?(coder: NSCoder) {
        fatalError("not supported")
    }
}

@objc(VlowGlass)
public final class VlowGlass: NSObject {
    @objc public static func makeModel() -> VlowGlassModel {
        VlowGlassModel()
    }

    /// Returns a hosting view sized (pill + blub margin); background drags
    /// still move the window. Call from the main thread.
    @MainActor
    @objc public static func makeView(_ model: VlowGlassModel) -> NSView {
        let host = DraggableHostingView(rootView: PillView(model: model))
        host.frame = NSRect(
            x: 0, y: 0,
            width: pillSize.width + 32, height: pillSize.height + 16
        )
        return host
    }
}
