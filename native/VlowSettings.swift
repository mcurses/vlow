// Settings window: a System Settings–style grouped form built with SwiftUI.
//
// Compiled into dist/libVlowGlass.dylib together with VlowGlass.swift and
// driven from Python (vlow/settings_window.py). Python hands over the current
// configuration as JSON and a target/selector; every change made in the
// window is debounced and sent back as JSON to that selector, where Python
// writes config.toml and applies the change live. No Save button — like
// System Settings, edits take effect as you make them.

import AppKit
import Combine
import SwiftUI

struct LocalModelInfo: Codable, Equatable {
    var key = ""
    var name = ""
    var size = ""
    var blurb = ""
}

struct SettingsData: Codable, Equatable {
    var hotkey = "fn"
    var mode = "toggle"
    var repaste_hotkey = ""  // pynput spec ("<ctrl>+<cmd>+v"); empty = no shortcut
    var paste_to_origin_app = true
    var backend = "mlx"
    var local_model = "whisper-large-v3"
    var auto_threshold_sec: Double = 60
    var assemblyai_api_key = ""
    var aai_language = ""
    var known_words: [String] = []
    var check_updates = true
    var config_path = ""
    var app_version = ""
    var local_models: [LocalModelInfo] = []  // read-only, from local_models.py
}

struct ModelStatus: Codable, Equatable {
    var model = ""  // LocalModelInfo.key
    var state = "unknown"  // missing | downloading | ready | error
    var progress: Double = 0
    var detail = ""
}

struct UpdateProgress: Codable, Equatable {
    var visible = false
    var fraction: Double? = nil  // nil while visible → indeterminate bar
}

struct KnownWord: Identifiable, Equatable {
    let id = UUID()
    var text: String
}

@objc(VlowSettingsModel)
public final class VlowSettingsModel: NSObject, ObservableObject {
    @Published var data = SettingsData()
    @Published var words: [KnownWord] = []
    @Published var modelStatus: [String: ModelStatus] = [:]  // by model key
    @Published var updateStatus = ""
    @Published var updateProgress = UpdateProgress()
    var onChange: ((String) -> Void)?
    var onAction: ((String) -> Void)?

    private var lastJSON = ""
    private var bag = Set<AnyCancellable>()

    override init() {
        super.init()
        Publishers.CombineLatest($data, $words)
            .debounce(for: .milliseconds(250), scheduler: RunLoop.main)
            .sink { [weak self] data, words in self?.emit(data, words) }
            .store(in: &bag)
    }

    func load(json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(SettingsData.self, from: raw)
        else { return }
        data = parsed
        words = parsed.known_words.map { KnownWord(text: $0) }
        lastJSON = canonical(parsed) ?? ""
    }

    private func canonical(_ d: SettingsData) -> String? {
        let enc = JSONEncoder()
        enc.outputFormatting = [.sortedKeys]
        guard let out = try? enc.encode(d) else { return nil }
        return String(decoding: out, as: UTF8.self)
    }

    private func emit(_ data: SettingsData, _ words: [KnownWord]) {
        var out = data
        out.known_words = words.map { $0.text.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard let json = canonical(out), json != lastJSON else { return }
        lastJSON = json
        onChange?(json)
    }
}

/// Records a keyboard shortcut and stores it as a pynput hotkey spec
/// ("<ctrl>+<cmd>+v"), the format `keyboard.GlobalHotKeys` in vlow/replay.py
/// parses. Click to record, press the combination (Escape cancels), the
/// x clears it.
private struct ShortcutRecorder: View {
    @Binding var spec: String
    @State private var recording = false
    @State private var monitor: Any?

    // pynput key names → the glyph macOS uses for them.
    private static let glyphs: [String: String] = [
        "ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘",
        "space": "Space", "enter": "↩", "tab": "⇥", "backspace": "⌫", "delete": "⌦",
        "esc": "⎋", "left": "←", "right": "→", "up": "↑", "down": "↓",
        "home": "↖", "end": "↘", "page_up": "⇞", "page_down": "⇟",
    ]
    // NSEvent key codes for keys that have no printable character.
    private static let specialKeys: [UInt16: String] = [
        49: "space", 36: "enter", 76: "enter", 48: "tab", 51: "backspace", 117: "delete",
        123: "left", 124: "right", 125: "down", 126: "up",
        115: "home", 119: "end", 116: "page_up", 121: "page_down",
        122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6", 98: "f7", 100: "f8",
        101: "f9", 109: "f10", 103: "f11", 111: "f12", 105: "f13", 107: "f14", 113: "f15",
        106: "f16", 64: "f17", 79: "f18", 80: "f19",
    ]

    static func display(_ spec: String) -> String {
        spec.split(separator: "+").map { part -> String in
            let name = part.trimmingCharacters(in: CharacterSet(charactersIn: "<>"))
            if let g = glyphs[name] { return g }
            return name.uppercased()
        }.joined()
    }

    var body: some View {
        HStack(spacing: 6) {
            Button {
                recording ? stop() : start()
            } label: {
                Text(recording ? "Press keys…" : (spec.isEmpty ? "Record Shortcut" : Self.display(spec)))
                    .frame(minWidth: 110)
                    .foregroundStyle(recording ? .secondary : .primary)
            }
            if !spec.isEmpty && !recording {
                Button {
                    spec = ""
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                }
                .buttonStyle(.borderless)
                .help("Remove the shortcut")
            }
        }
        .onDisappear { stop() }
    }

    private func start() {
        recording = true
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {  // Escape cancels
                stop()
                return nil
            }
            if let parsed = Self.parse(event) {
                spec = parsed
                stop()
                return nil
            }
            NSSound.beep()  // needs a modifier + a real key
            return nil
        }
    }

    private func stop() {
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
        recording = false
    }

    /// nil when the event isn't usable as a global shortcut.
    static func parse(_ event: NSEvent) -> String? {
        parse(keyCode: event.keyCode, flags: event.modifierFlags, characters: event.charactersIgnoringModifiers)
    }

    static func parse(keyCode: UInt16, flags rawFlags: NSEvent.ModifierFlags, characters: String?) -> String? {
        let flags = rawFlags.intersection(.deviceIndependentFlagsMask)
        var parts: [String] = []
        if flags.contains(.control) { parts.append("<ctrl>") }
        if flags.contains(.option) { parts.append("<alt>") }
        if flags.contains(.shift) { parts.append("<shift>") }
        if flags.contains(.command) { parts.append("<cmd>") }
        // Shift alone would swallow ordinary typing; require a real modifier.
        guard parts.contains(where: { $0 != "<shift>" }) else { return nil }

        if let special = specialKeys[keyCode] {
            parts.append("<\(special)>")
            return parts.joined(separator: "+")
        }
        guard let chars = characters?.lowercased(),
              chars.count == 1,
              let ch = chars.first,
              ch != "+", !ch.isWhitespace, !ch.isNewline,
              ch.isLetter || ch.isNumber || ch.isPunctuation || ch.isSymbol
        else { return nil }
        parts.append(String(ch))
        return parts.joined(separator: "+")
    }
}

private struct SettingsView: View {
    @ObservedObject var model: VlowSettingsModel
    @State private var selectedWord: KnownWord.ID?

    private var hotkeyName: String {
        switch model.data.hotkey {
        case "right_opt": return "Right Option"
        case "left_opt": return "Left Option"
        case "right_cmd": return "Right Command"
        default: return "Fn"
        }
    }

    var body: some View {
        Form {
            Section {
                Picker("Hotkey", selection: $model.data.hotkey) {
                    Text("Fn / Globe").tag("fn")
                    Text("Right Option").tag("right_opt")
                    Text("Left Option").tag("left_opt")
                    Text("Right Command").tag("right_cmd")
                }
                Picker("Mode", selection: $model.data.mode) {
                    Text("Toggle").tag("toggle")
                    Text("Push to talk").tag("ptt")
                }
                LabeledContent {
                    ShortcutRecorder(spec: $model.data.repaste_hotkey)
                } label: {
                    Text("Re-paste last")
                    Text("Pastes the most recent transcription again")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Toggle(isOn: $model.data.paste_to_origin_app) {
                    Text("Paste into the app I started in")
                    Text("Double-tap recordings go back to the app that was in front when you started, then focus returns to where you are")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } header: {
                Text("Dictation")
            } footer: {
                if model.data.mode == "ptt" {
                    Text("Hold \(hotkeyName) to stream live via AssemblyAI; release to stop.")
                } else {
                    Text("Double-tap \(hotkeyName) to start recording and again to stop and paste. Hold it to stream live via AssemblyAI.")
                }
            }

            Section {
                Picker("Backend", selection: $model.data.backend) {
                    Text("On-device (MLX)").tag("mlx")
                    Text("AssemblyAI (cloud)").tag("assemblyai")
                    Text("Auto — by duration").tag("auto")
                }
                if model.data.backend == "auto" {
                    LabeledContent("Send to cloud above") {
                        HStack(spacing: 4) {
                            TextField(
                                "", value: $model.data.auto_threshold_sec,
                                format: .number.precision(.fractionLength(0))
                            )
                            .frame(width: 56)
                            .multilineTextAlignment(.trailing)
                            Stepper(
                                "", value: $model.data.auto_threshold_sec,
                                in: 5...3600, step: 5
                            )
                            .labelsHidden()
                            Text("seconds").foregroundStyle(.secondary)
                        }
                    }
                }
            } header: {
                Text("Transcription")
            } footer: {
                switch model.data.backend {
                case "mlx":
                    Text("Runs entirely on this Mac using the on-device model selected below.")
                case "assemblyai":
                    Text("Every recording is uploaded to AssemblyAI.")
                default:
                    Text("Short recordings stay on-device; longer ones are uploaded to AssemblyAI.")
                }
            }

            Section {
                Picker("Model", selection: $model.data.local_model) {
                    ForEach(model.data.local_models, id: \.key) { m in
                        Text(m.name).tag(m.key)
                    }
                }
                ForEach(model.data.local_models, id: \.key) { m in
                    let st = model.modelStatus[m.key] ?? ModelStatus()
                    LabeledContent {
                        switch st.state {
                        case "ready":
                            Label("Ready", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                                .labelStyle(.titleAndIcon)
                        case "downloading":
                            HStack(spacing: 8) {
                                ProgressView(value: st.progress)
                                    .frame(width: 140)
                                Text(st.progress.formatted(.percent.precision(.fractionLength(0))))
                                    .monospacedDigit()
                                    .foregroundStyle(.secondary)
                                    .frame(width: 40, alignment: .trailing)
                            }
                        case "error":
                            Button("Retry Download") { model.onAction?("downloadModel:\(m.key)") }
                        default:
                            Button("Download…") { model.onAction?("downloadModel:\(m.key)") }
                        }
                    } label: {
                        Text(m.name)
                        Text(st.detail.isEmpty ? m.size : st.detail)
                            .font(.caption)
                            .foregroundStyle(st.state == "error" ? .red : .secondary)
                    }
                }
            } header: {
                Text("On-device model")
            } footer: {
                let blurb = model.data.local_models.first { $0.key == model.data.local_model }?.blurb ?? ""
                Text(blurb + (blurb.isEmpty ? "" : " ") + "Needed for the on-device and auto backends; downloaded once from Hugging Face into ~/.cache/huggingface. The AssemblyAI backend works without it.")
            }

            Section {
                SecureField("API key", text: $model.data.assemblyai_api_key)
                TextField(
                    "Language", text: $model.data.aai_language,
                    prompt: Text("auto-detect")
                )
            } header: {
                Text("AssemblyAI")
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Needed for the hold-to-stream gesture and for the cloud and auto backends. Language is an ISO 639-1 code such as de or en; leave it empty to auto-detect.")
                    Link("Get an API key…", destination: URL(string: "https://www.assemblyai.com/dashboard/api-keys")!)
                }
            }

            Section {
                List(selection: $selectedWord) {
                    ForEach($model.words) { $word in
                        TextField("Word or name", text: $word.text)
                            .textFieldStyle(.plain)
                    }
                }
                .frame(minHeight: 120, maxHeight: 160)
                .alternatingRowBackgrounds()
                HStack(spacing: 0) {
                    Button {
                        let w = KnownWord(text: "")
                        model.words.append(w)
                        selectedWord = w.id
                    } label: {
                        Image(systemName: "plus").frame(width: 24, height: 20)
                    }
                    Divider().frame(height: 14)
                    Button {
                        if let id = selectedWord {
                            model.words.removeAll { $0.id == id }
                            selectedWord = nil
                        }
                    } label: {
                        Image(systemName: "minus").frame(width: 24, height: 20)
                    }
                    .disabled(selectedWord == nil)
                    Spacer()
                }
                .buttonStyle(.borderless)
            } header: {
                Text("Known words")
            } footer: {
                Text("Names and terms every backend is nudged toward. Applied from the next recording on.")
            }

            Section {
                LabeledContent {
                    Button("Check Now") { model.onAction?("checkUpdates") }
                        .disabled(model.updateProgress.visible)
                } label: {
                    Text("Version \(model.data.app_version)")
                    if !model.updateStatus.isEmpty {
                        Text(model.updateStatus).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if model.updateProgress.visible {
                    HStack(spacing: 8) {
                        if let f = model.updateProgress.fraction {
                            ProgressView(value: f)
                            Text(f.formatted(.percent.precision(.fractionLength(0))))
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                                .frame(width: 40, alignment: .trailing)
                        } else {
                            ProgressView()
                                .progressViewStyle(.linear)
                        }
                    }
                }
                Toggle("Check for updates automatically", isOn: $model.data.check_updates)
            } header: {
                Text("Updates")
            } footer: {
                Text("Updates come from the vlow GitHub releases. Installing one downloads it, replaces the app and relaunches it. The downloaded app is ad-hoc signed, so macOS asks for Accessibility again afterwards; a source checkout pulls, syncs and rebuilds instead.")
            }

            Section {
                LabeledContent("Config file") {
                    Button("Show in Finder") {
                        NSWorkspace.shared.selectFile(model.data.config_path, inFileViewerRootedAtPath: "")
                    }
                }
            } footer: {
                Text(model.data.config_path)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
    }
}

@objc(VlowSettings)
public final class VlowSettings: NSObject {
    private static var window: NSWindow?
    private static let model = VlowSettingsModel()
    /// The app that was in front before Settings took over; it gets focus
    /// back when the window closes (vlow has no other windows, so macOS
    /// would otherwise leave vlow active with nothing to type into).
    private static var previousApp: NSRunningApplication?

    /// Show (or bring forward) the settings window. `json` is the current
    /// configuration; each change is delivered as JSON to
    /// `[target performSelector:selector withObject:json]` on the main thread,
    /// button presses (e.g. "downloadModel") to `actionSelector` as a string.
    @MainActor
    @objc(show:target:selector:actionSelector:)
    public static func show(_ json: String, target: NSObject, selector: String, actionSelector: String) {
        model.load(json: json)
        let sel = NSSelectorFromString(selector)
        let actionSel = NSSelectorFromString(actionSelector)
        model.onChange = { [weak target] out in
            _ = target?.perform(sel, with: out as NSString)
        }
        model.onAction = { [weak target] name in
            _ = target?.perform(actionSel, with: name as NSString)
        }
        if let front = NSWorkspace.shared.frontmostApplication,
           front.processIdentifier != ProcessInfo.processInfo.processIdentifier {
            previousApp = front
        }
        if window == nil {
            let host = NSHostingController(rootView: SettingsView(model: model))
            let w = NSWindow(contentViewController: host)
            w.title = "vlow Settings"
            w.styleMask = [.titled, .closable, .miniaturizable, .resizable]
            w.isReleasedWhenClosed = false
            w.contentMinSize = NSSize(width: 520, height: 480)
            w.contentMaxSize = NSSize(width: 520, height: 2000)
            let screenH = NSScreen.main?.visibleFrame.height ?? 900
            w.setContentSize(NSSize(width: 520, height: min(860, screenH - 60)))
            w.center()
            NotificationCenter.default.addObserver(
                forName: NSWindow.willCloseNotification, object: w, queue: .main
            ) { _ in
                let me = ProcessInfo.processInfo.processIdentifier
                guard NSWorkspace.shared.frontmostApplication?.processIdentifier == me,
                      let prev = previousApp, !prev.isTerminated else { return }
                prev.activate(options: [.activateIgnoringOtherApps])
            }
            window = w
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    @MainActor
    @objc(setUpdateStatus:)
    public static func setUpdateStatus(_ text: String) {
        model.updateStatus = text
    }

    /// Progress bar under the Updates row: {"visible": bool, "fraction": 0…1 | null}.
    @MainActor
    @objc(setUpdateProgress:)
    public static func setUpdateProgress(_ json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(UpdateProgress.self, from: raw)
        else { return }
        model.updateProgress = parsed
    }

    /// Update one on-device model row: {"model","state","progress","detail"}.
    @MainActor
    @objc(setModelStatus:)
    public static func setModelStatus(_ json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(ModelStatus.self, from: raw)
        else { return }
        model.modelStatus[parsed.model] = parsed
    }

    /// Replace the window's contents (e.g. after config.toml changed on disk).
    @MainActor
    @objc(update:)
    public static func update(_ json: String) {
        model.load(json: json)
    }

    @MainActor
    @objc public static func isVisible() -> Bool {
        window?.isVisible ?? false
    }

    /// Test hooks for the shortcut recorder: build the pynput spec the way a
    /// key event would, and render a spec the way the button shows it.
    /// Returns "" when the combination is not usable as a shortcut.
    @objc(shortcutSpecForKeyCode:flags:characters:)
    public static func shortcutSpec(forKeyCode keyCode: UInt16, flags: UInt, characters: String) -> String {
        ShortcutRecorder.parse(keyCode: keyCode, flags: NSEvent.ModifierFlags(rawValue: flags), characters: characters) ?? ""
    }

    @objc(shortcutDisplay:)
    public static func shortcutDisplay(_ spec: String) -> String {
        ShortcutRecorder.display(spec)
    }

    /// Test hook: apply `json` as if the user had edited the form, so the
    /// debounced change callback fires without UI interaction.
    @MainActor
    @objc(simulateEdit:)
    public static func simulateEdit(_ json: String) {
        guard let raw = json.data(using: .utf8),
              let parsed = try? JSONDecoder().decode(SettingsData.self, from: raw)
        else { return }
        model.data = parsed
        model.words = parsed.known_words.map { KnownWord(text: $0) }
    }
}
