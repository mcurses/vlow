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
                // Crossfade between the mode's bar sources so a state switch
                // never snaps — the frozen recording bars melt into the wave.
                func source(_ mode: String, _ i: Int) -> Double {
                    switch mode {
                    case "busy": return 0.30 + 0.24 * sin(t * 7.0 + Double(i) * 0.48)
                    case "record": return model.levels[i]
                    default: return 0
                    }
                }
                let p = min(1.0, max(0.0, (t - model.modeChangedAt) / 0.55))
                let blend = p * p * (3 - 2 * p)  // smoothstep
                for i in 0..<barCount {
                    let level = source(model.previousMode, i) * (1 - blend)
                        + source(model.mode, i) * blend
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
